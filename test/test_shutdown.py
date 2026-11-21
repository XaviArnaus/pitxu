"""The closing of the application: write-ahead of the summary, lock of a dead process, signals."""
import ast
import os
import shutil
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403

HIST = [{"role": "user", "text": "hello"}, {"role": "model", "text": "hi"}]


def summ(config):
    return Summarizer(config=config, params=params(language="en"))


class ShutdownTests(unittest.TestCase):
    def setUp(self):
        self._real_llm = Memory.request_llm_json
        Memory.request_llm_json = fake_llm
        reset_fake()

    def tearDown(self):
        Memory.request_llm_json = self._real_llm

    def test_01_in_flight_rows_wait_for_the_closing(self):
        """in-flight rows are invisible to the consolidation until released"""
        tmp,C,W,con=env()
        pid=W.create_pending_conversation(HIST,language="en",in_flight=True)
        check("in-flight excluded from the pending list",W.get_pending_conversations()==[])
        FAKE["summarize"]={"significant":True,"summary":"Plans","content":"x"}
        con.run("a"); check("the consolidation did not summarize it (no summarization call)","summarization" not in FAKE["calls"] and q(W,"select attempts from pending_conversations where id=?",pid)[0]["attempts"]==-1)
        check("startup releases it",W.release_in_flight_conversations()==1 and len(W.get_pending_conversations())==1)
        con.run("b"); check("then the nightly consolidation summarizes it",W.get_pending_conversations()==[] and q(W,"select count(*) n from short_time_memory where summary='Plans'")[0]["n"]>=1)
    def test_02_summarizer_settles_the_write_ahead_row(self):
        """the summarizer settles the write-ahead row"""
        tmp,C,W,con=env(); S=summ(C)
        a=W.create_pending_conversation(HIST,in_flight=True); FAKE["summarize"]={"significant":True,"summary":"Trip","content":"Rome"}
        S.summarize_and_store_in_memory(HIST,pending_id=a)
        check("success: summary stored, row deleted",q(W,"select count(*) n from pending_conversations")[0]["n"]==0 and q(W,"select count(*) n from short_time_memory where summary='Trip'")[0]["n"]==1)
        b=W.create_pending_conversation(HIST,in_flight=True); FAKE["summarize"]={"significant":False}
        S.summarize_and_store_in_memory(HIST,pending_id=b); check("not significant: row deleted, nothing stored",q(W,"select count(*) n from pending_conversations")[0]["n"]==0)
        c=W.create_pending_conversation(HIST,in_flight=True); FAKE["summarize"]=None
        S.summarize_and_store_in_memory(HIST,pending_id=c)
        r=q(W,"select attempts from pending_conversations"); check(f"LLM failure: the same row is released, no second copy: {r}",len(r)==1 and r[0]["attempts"]==0)
        W.db.connection.execute("delete from pending_conversations"); W.db.connection.commit()
        d=W.create_pending_conversation(HIST,in_flight=True)
        def boom(*a,**k): raise RuntimeError("boom")
        S.memory.summarize_chatbot_history_as_memory_entry=boom
        try: S.summarize_and_store_in_memory(HIST,pending_id=d)
        except RuntimeError: pass
        check("an exception releases the row too",q(W,"select attempts from pending_conversations where id=?",d)[0]["attempts"]==0)
        S2=summ(C); FAKE["summarize"]=None; before=q(W,"select count(*) n from pending_conversations")[0]["n"]
        S2.summarize_and_store_in_memory(HIST)   # old path without write-ahead: still saves a raw copy
        check("without a pending_id the old fallback still keeps the raw copy",q(W,"select count(*) n from pending_conversations")[0]["n"]==before+1)
    def test_03_lock_of_a_dead_process_is_taken_over(self):
        """the lock of a dead process is taken over"""
        tmp,C,W,con=env()
        check("lock taken, value carries the pid",W.acquire_consolidation_lock(7200) and W.get_meta(Memory.META_CONSOLIDATION_LOCK).endswith("|%d"%os.getpid()))
        check("alive holder (this process) keeps it",W.acquire_consolidation_lock(7200) is False)
        import subprocess
        dead=subprocess.Popen(["true"]); dead.wait()
        W.set_meta(Memory.META_CONSOLIDATION_LOCK,"%s|%d"%(datetime.now().isoformat(),dead.pid))
        check("holder gone: taken over even though not expired",W.acquire_consolidation_lock(7200) is True and W.get_meta(Memory.META_CONSOLIDATION_LOCK).endswith("|%d"%os.getpid()))
        W.set_meta(Memory.META_CONSOLIDATION_LOCK,datetime.now().isoformat())
        check("legacy value without pid: only the ttl counts",W.acquire_consolidation_lock(7200) is False)
        W.set_meta(Memory.META_CONSOLIDATION_LOCK,(datetime.now()-timedelta(hours=3)).isoformat()+"|%d"%os.getpid())
        check("expired ttl is still taken over",W.acquire_consolidation_lock(7200) is True)
    def test_04_main_closing_summary_and_signal_handler(self):
        """Main: closing summary with write-ahead, and the signal handler (methods extracted from main.py)"""
        tree=ast.parse(open(os.path.join(REPO, "pitxu/main.py")).read())
        wanted={"_summarize_current_conversation","_keep_conversation_before_closing","_summarize_in_process","_handle_signal"}
        fns=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in wanted]
        check("all four methods found",len(fns)==4)
        mod=ast.Module(body=[ast.ClassDef(name="M",bases=[],keywords=[],body=fns,decorator_list=[],type_params=[])],type_ignores=[])
        ast.fix_missing_locations(mod)
        import signal
        G={"signal":signal,"sys":sys,"Dictionary":Dictionary,"Config":Config}
        exec(compile(mod,"main_methods","exec"),G)
        M=G["M"]
        class Log:
            def __init__(s): s.lines=[]
            def info(s,m): s.lines.append(m)
            warning=error=debug=info
        class FakeInter:
            def __init__(s,alive=True,finish=True): s.alive=alive; s.finish=finish; s.waited=[]
            def is_support_process_alive(s): return s.alive
            def wait_for_support_process_to_finish(s,timeout=None,should_stop=None): s.waited.append((timeout,should_stop)); return s.finish
        class FakeSupport:
            def __init__(s): s.sent=[]
            def summarize_and_store_in_memory(s,history,pending_id=None): s.sent.append((history,pending_id))
        class FakeChatbot:
            def get_chat_history_as_list_of_dicts(s,curated=True): return HIST
        def mk(C,**kw):
            m=M(); m._xlog=Log(); m._log_debug=lambda x:None; m._xconfig=C
            m._xparams=Dictionary({"api_key":"k","base_path":REPO,"language":"en","execution_mode":"x"})
            m._chatbot=FakeChatbot(); m._history_summarized_upto=0; m._interaction=kw.get("inter",FakeInter()); m._support=FakeSupport()
            m._skip_summary_wait=False; m._exit_requested=False; m._run_loop_active=False; m._is_pitxu_active=True
            return m
        tmp,C,W,con=env()
        m=mk(C)
        check("closing (wait=True) writes the in-flight copy and sends its id",m._summarize_current_conversation("closing",wait=True) and m._support.sent[0][1] is not None
              and q(W,"select attempts from pending_conversations where id=?",m._support.sent[0][1])[0]["attempts"]==-1)
        check("the wait is interruptible by the second signal",callable(m._interaction.waited[0][1]) and m._interaction.waited[0][1]() is False)
        m._skip_summary_wait=True; check("... and the hook reflects the flag",m._interaction.waited[0][1]() is True)
        m2=mk(C,inter=FakeInter(finish=False)); m2._summarize_current_conversation("closing",wait=True)
        check("a timeout is logged with the pending id",any("did not finish" in l and "pending conversation #" in l for l in m2._xlog.lines))
        m3=mk(C); m3._summarize_current_conversation("end of conversation",wait=False)
        check("normal end of conversation: no write-ahead, plain send",m3._support.sent[0][1] is None)
        C_off=cfg(tmp,**{"memory.summarization.fallback_save_raw":False}); m4=mk(C_off); m4._summarize_current_conversation("closing",wait=True)
        check("write-ahead respects fallback_save_raw=False",m4._support.sent[0][1] is None)
        # in-process fallback passes the id to the summarizer (stub the summarizer module)
        calls=[]
        class FakeSumm:
            def __init__(s,**k): pass
            def summarize_and_store_in_memory(s,h,pending_id=None): calls.append(pending_id)
            def close(s): pass
        fm=types.ModuleType("pitxu.lib.support_process.summarizer"); fm.Summarizer=FakeSumm; keep=sys.modules["pitxu.lib.support_process.summarizer"]; sys.modules["pitxu.lib.support_process.summarizer"]=fm
        m5=mk(C,inter=FakeInter(alive=False)); m5._summarize_current_conversation("closing",wait=True); sys.modules["pitxu.lib.support_process.summarizer"]=keep
        check("Support gone: summarized in-process with the same pending id",len(calls)==1 and calls[0] is not None)

        h=mk(C); closed=[]; h.close_nicely=lambda *a,**k: closed.append(1)
        h._handle_signal(signal.SIGTERM,None); check("before the run loop: the handler closes by itself",closed==[1] and not h._exit_requested)
        h=mk(C); closed=[]; h.close_nicely=lambda *a,**k: closed.append(1); h._run_loop_active=True
        h._handle_signal(signal.SIGTERM,None); check("run loop active: the handler only asks, nothing closes inside it",closed==[] and h._exit_requested is True)
        h=mk(C); h._is_pitxu_active=False; closed=[]; h.close_nicely=lambda *a,**k: closed.append(1)
        h._handle_signal(signal.SIGINT,None); check("second signal while closing: skip the summary wait, no second close",h._skip_summary_wait is True and closed==[])
    def test_05_interruptible_wait(self):
        """the interruptible wait (method extracted from interaction.py)"""
        tree=ast.parse(open(os.path.join(REPO, "pitxu/lib/interaction/interaction.py")).read())
        fn=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=="wait_for_support_process_to_finish"][0]
        mod=ast.Module(body=[ast.ClassDef(name="I",bases=[],keywords=[],body=[fn],decorator_list=[],type_params=[])],type_ignores=[]); ast.fix_missing_locations(mod)
        G2={"threading":threading,"time":time,"QUEUE_SUPPORT":"support","SHARED_SUPPORT_BUSY":1}; exec(compile(mod,"inter","exec"),G2); I=G2["I"]
        class Q:
            def __init__(s,secs): s.secs=secs
            def join(s): time.sleep(s.secs)
        class Pool:
            def __init__(s,secs): s.q=Q(secs)
            def get_queue(s,n): return s.q
        def mi(secs):
            i=I(); i.process_pool=Pool(secs); i._xlog=Log(); return i
        t=time.monotonic(); r=mi(0.3).wait_for_support_process_to_finish(timeout=5); check("finishes when the queue is done",r is True and time.monotonic()-t<4)
        t=time.monotonic(); r=mi(5).wait_for_support_process_to_finish(timeout=1); check("gives up at the timeout",r is False and 0.9<time.monotonic()-t<4)
        flag={"v":False}; threading.Timer(0.6,lambda: flag.update(v=True)).start()
        t=time.monotonic(); r=mi(5).wait_for_support_process_to_finish(timeout=10,should_stop=lambda:flag["v"]); check("gives up as soon as it is asked to stop",r is False and time.monotonic()-t<4)
    def test_06_service_file(self):
        """the service file"""
        C = cfg(tempfile.mkdtemp())
        svc=open(os.path.join(REPO, "config/system/pitxu.service")).read(); check("TimeoutStopSec=120 above the close timeout",any(l.strip()=="TimeoutStopSec=120" for l in svc.splitlines()) and float(C.get("memory.summarization.close_timeout_seconds"))<120)
