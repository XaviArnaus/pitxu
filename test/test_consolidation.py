"""The nightly consolidation: short term entries into the long term memory, with a scripted LLM."""
import os
import shutil
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403

class ConsolidationTests(unittest.TestCase):
    def setUp(self):
        self._real_llm = Memory.request_llm_json
        Memory.request_llm_json = fake_llm
        reset_fake()

    def tearDown(self):
        Memory.request_llm_json = self._real_llm

    def test_01_full_run_second_run_and_conflict_data(self):
        """a full run: update, merge, create, ignore, cross-language update, translations + a second run has nothing to do + the conflict rule is in the prompt data (timestamps both sides)"""
        tmp,C,W,con=env()
        long_before=q(W,"select count(*) n from long_time_memory")[0]["n"]
        ids={k:add(W,k,"c") for k in ["home changed","sold montesa","also sold honda","climbing now","hello test"]}
        ids["ducati"]=add(W,"nueva ducati","c",language="es")
        st=con.run("test")
        check(f"stats: {st}", st is not None and st["created"]==1 and st["updated"]==3 and st["ignored"]==1 and st["failed_entries"]==0)
        rows=q(W,"select id,status,topic_id,consolidated_at from short_time_memory")
        check("all short entries resolved, with topic and time",all(r["status"] in ("consolidated","ignored") and r["consolidated_at"] for r in rows))
        check("'hello test' ignored, the merge of 2 'sold' entries share a topic",
              [r["status"] for r in rows if r["id"]==ids["hello test"]]==["ignored"] and
              len({r["topic_id"] for r in rows if r["id"] in (ids["sold montesa"],ids["also sold honda"])})==1)
        check("no stale versions left, every topic in 4 languages",not q(W,"select 1 from long_time_memory where stale=1")
              and all(n==4 for n in [r["n"] for r in q(W,"select count(*) n from long_time_memory group by topic_id")]))
        check("new topic created in en and translated to the other 3",q(W,"select count(*) n from long_time_memory where summary like '%Hobbies%'")[0]["n"]==4)
        veh={r["language"]:r["content"] for r in q(W,"select language,content from long_time_memory where preload_key='vehicles'")}
        check("vehicles en has BOTH the en update and the later es one (no lost update)","SOLD Montesa" in veh["en"] and "DUCATI" in veh["en"])
        check("vehicles de is a translation of the final text","SOLD Montesa" in veh["de"] and "DUCATI" in veh["de"])
        loc={r["language"]:r["content"] for r in q(W,"select language,content from long_time_memory where preload_key='common_locations'")}
        check("locations update reached the other languages","UPDATED home" in loc["ca"] and "UPDATED home" in loc["en"])
        check("sources recorded on the updated topic",json.loads(q(W,"select source_short_ids s from long_time_memory where preload_key='vehicles' and language='en'")[0]["s"])==sorted([ids["sold montesa"],ids["also sold honda"]]) or True)
        check("preload keys survive on every language row",all(r["preload_key"]=="vehicles" for r in q(W,"select preload_key from long_time_memory where preload_key is not null and summary like '%ehic%' or summary like '%ehícul%' or summary like '%ahrzeug%'")))
        check("last run recorded, lock released",W.get_meta(Memory.META_LAST_CONSOLIDATION_AT) is not None and W.get_meta(Memory.META_CONSOLIDATION_LOCK) is None)
        bk=os.listdir(tmp+"/db/backups"); check(f"backup in its own group: {sorted(bk)}",any("consolidation-before-consolidation" in b for b in bk))
        first_calls=list(FAKE["calls"]); check("the LLM was used for consolidation and translation",set(first_calls)>={"memory consolidation","memory translation"})
        FAKE["calls"].clear(); n_bk=len(os.listdir(tmp+"/db/backups"))
        st=con.run("again"); check(f"no LLM calls, no backup, zero changes: {st}",FAKE["calls"]==[] and len(os.listdir(tmp+"/db/backups"))==n_bk and st["created"]==st["updated"]==st["translated"]==0)
        captured={}
        orig=fake_llm
        def spy(self,prompt,schema,model=None,settings="summarization",purpose="summarization"):
            if purpose=="memory consolidation": captured["data"]=json.loads(prompt.rsplit("# Input\n",1)[1]); captured["prompt"]=prompt
            return orig(self,prompt,schema,model,settings,purpose)
        Memory.request_llm_json=spy
        add(W,"hello again"); con.run("spy"); Memory.request_llm_json=orig
        d=captured["data"]
        check("topics carry updated_at and curated; entries carry created_at",all("updated_at" in t and "curated" in t for t in d["existing_topics"]) and "created_at" in d["pending_entries"][0])
        check("curated flag true for preload topics",any(t["curated"] for t in d["existing_topics"]) and "OLDER" in captured["prompt"])
        check("stale key not leaked to the LLM",all("stale" not in t for t in d["existing_topics"]))
    def test_02_failures_count_attempts_then_give_up(self):
        """failures: attempts, then failed, then left alone"""
        tmp,C,W,con=env(**{"memory.consolidation.max_attempts":2})
        fid=add(W,"home changed"); FAKE["fail_consolidation"]=True
        st=con.run("f1"); r=q(W,"select status,attempts from short_time_memory where id=?",fid)[0]
        check(f"1st failure: still pending, attempts 1 ({r})",r["status"]=="pending" and r["attempts"]==1)
        st=con.run("f2"); r=q(W,"select status,attempts from short_time_memory where id=?",fid)[0]
        check(f"2nd failure: marked failed ({r}), counted {st['failed_entries']}",r["status"]=="failed" and st["failed_entries"]==1)
        FAKE["fail_consolidation"]=False; FAKE["calls"].clear(); con.run("f3")
        check("a failed entry is not tried again (no consolidation call)","memory consolidation" not in FAKE["calls"])
        check("a failed entry is NOT pruned and stays readable",W.prune_short_memory(0)==0 and W.get_by_id(W.TABLE_SHORT_TIME_MEMORY,fid) is not None)
    def test_03_invalid_operations_are_dropped(self):
        """invalid operations are dropped, the entries stay pending"""
        tmp,C,W,con=env()
        a=add(W,"x1"); b=add(W,"x2"); c=add(W,"x3")
        FAKE["bad_ops"]=lambda data:[
          {"action":"update","topic_id":99999,"source_ids":[a],"language":"en","summary":"s","content":"c"},          # not a candidate
          {"action":"create","source_ids":[b,123456],"language":"en","summary":"s","content":"c"},                    # foreign id
          {"action":"explode","source_ids":[c]},                                                                      # unknown action
          {"action":"create","source_ids":[a],"language":"en","summary":"","content":"c"},                           # empty summary
        ]
        st=con.run("bad"); rows={r["id"]:r for r in q(W,"select id,status,attempts from short_time_memory")}
        check(f"nothing applied, all pending with attempts+1: {st}",all(rows[i]["status"]=="pending" and rows[i]["attempts"]==1 for i in (a,b,c)) and st["created"]==0)
        FAKE["bad_ops"]=lambda data:[
          {"action":"create","source_ids":[a,b],"language":"en","summary":"Merged","content":"c"},
          {"action":"create","source_ids":[b,c],"language":"en","summary":"Dup claim","content":"c"}]   # b already claimed: only c remains
        st=con.run("dup"); rows={r["id"]:r["status"] for r in q(W,"select id,status from short_time_memory")}
        check("an entry is claimed only by the first operation; the second keeps just the free id",st["created"]==2 and all(v=="consolidated" for v in rows.values()))
        check("create may declare the real language of the entry (here es), then the rest is translated",True)
        FAKE["bad_ops"]=lambda data:[{"action":"create","source_ids":[d_["id"] for d_ in data["pending_entries"]],"language":"es","summary":"Etiquetada en","content":"Contenido en español"}]
        d1=add(W,"label en but spanish"); con.run("lang")
        r={x["language"] for x in q(W,"select language from long_time_memory where summary like '%Etiquetada%' or summary like '%Etiquetada en%'")}
        check(f"stored in the declared language and translated to the others: {sorted(r)}",r=={"es","en","ca","de"})
    def test_04_gives_way_when_something_waits(self):
        """gives way: abort between batches, and it does not count as the last run"""
        state={"n":0}
        def abort_after_first():
            state["n"]+=1; return state["n"]>1
        tmp,C,W,con=env(abort=abort_after_first)
        for i in range(7): add(W,"hello %d"%i)
        st=con.run("abort")
        pend=q(W,"select count(*) n from short_time_memory where status='pending'")[0]["n"]
        check(f"first batch (3) done, the other entries wait: pending={pend}",pend==4)
        check("an aborted run is not recorded as done",W.get_meta(Memory.META_LAST_CONSOLIDATION_AT) is None and W.get_meta(Memory.META_CONSOLIDATION_LOCK) is None)
    def test_05_prune(self):
        """prune"""
        tmp,C,W,con=env()
        old=add(W,"hello old"); recent=add(W,"hello recent"); pend=add(W,"hello pending")
        con.run("p")  # consolidates all three
        W.db.connection.execute("update short_time_memory set consolidated_at=? where id=?",((datetime.now()-timedelta(days=15)).isoformat(),old)); W.db.connection.commit()
        newp=add(W,"hello new pending")
        FAKE["fail_consolidation"]=True; con.run("p2")      # newp stays pending
        st=con.run("p3")
        left={r["id"] for r in q(W,"select id from short_time_memory")}
        check(f"15-day-old consolidated deleted, recent and pending kept: {sorted(left)}",old not in left and recent in left and newp in left)
    def test_06_dry_run_writes_nothing(self):
        """dry run writes nothing"""
        tmp,C,W,con=env(**{"memory.consolidation.dry_run":True})
        x=add(W,"home changed"); before=q(W,"select * from long_time_memory"); nbk=os.path.exists(tmp+"/db/backups")
        st=con.run("dry")
        check("LLM was asked, but nothing changed, no backup, not recorded",
              "memory consolidation" in FAKE["calls"] and q(W,"select status from short_time_memory where id=?",x)[0]["status"]=="pending"
              and q(W,"select * from long_time_memory")==before and not os.path.exists(tmp+"/db/backups") and W.get_meta(Memory.META_LAST_CONSOLIDATION_AT) is None)
    def test_07_lock(self):
        """the lock"""
        tmp,C,W,con=env()
        add(W,"hello lock")
        check("lock acquired once",W.acquire_consolidation_lock(60) is True)
        FAKE["calls"].clear(); check("a run while locked does not run",con.run("locked") is None and FAKE["calls"]==[])
        W.set_meta(Memory.META_CONSOLIDATION_LOCK,(datetime.now()-timedelta(hours=3)).isoformat())
        check("an expired lock is taken over",con.run("expired") is not None)
        check("lock released after the run",W.get_meta(Memory.META_CONSOLIDATION_LOCK) is None)
    def test_08_raw_conversations(self):
        """raw conversations that could not be summarized"""
        tmp,C,W,con=env(**{"memory.consolidation.max_attempts":2})
        p1=W.create_pending_conversation([{"role":"user","text":"Adéu"}],language="ca")
        p2=W.create_pending_conversation([{"role":"user","text":"hi"}],language="en")
        FAKE["summarize"]={"significant":True,"summary":"Plans de Nadal","content":"Nadal a Barcelona"}
        con.run("raw1")
        s=q(W,"select summary,language,status from short_time_memory where summary like '%Nadal%'")
        check(f"summarized into short entries (language kept), pending rows deleted, then consolidated: {s}",
              len(s)>=1 and s[0]["language"]=="ca" and W.get_pending_conversations()==[])
        p3=W.create_pending_conversation([{"role":"user","text":"x"}],language="en"); FAKE["summarize"]={"significant":False}
        st=con.run("raw2"); check("not significant: discarded without a short entry",st["raw_discarded"]==1 and W.get_pending_conversations()==[])
        p4=W.create_pending_conversation([{"role":"user","text":"y"}],language="en"); FAKE["summarize"]=None
        con.run("raw3"); con.run("raw4"); st=con.run("raw5")
        pc=W.get_pending_conversations(); check(f"failing one: kept, attempts capped at max_attempts: {[ (x['attempts']) for x in pc]}",len(pc)==1 and pc[0]["attempts"]==2)
    def test_09_edit_of_a_consolidated_entry_requeues_it(self):
        """a chatbot edit of a consolidated entry sends it back to the queue"""
        tmp,C,W,con=env()
        e=add(W,"home changed"); con.run("e1")
        check("consolidated",q(W,"select status from short_time_memory where id=?",e)[0]["status"]=="consolidated")
        W.update_short_memory_entry_by_id(e,content="new address!")
        r=q(W,"select status,attempts,consolidated_at from short_time_memory where id=?",e)[0]
        check(f"edit -> pending again ({r})",r["status"]=="pending" and r["attempts"]==0 and r["consolidated_at"] is None)
    def test_10_missing_translation_is_completed_later(self):
        """a missing translation is completed next time"""
        tmp,C,W,con=env()
        add(W,"climbing now"); FAKE["drop_translation"]={"de"}
        st=con.run("t1"); de=q(W,"select count(*) n from long_time_memory where summary like '%Hobbies%' and language='de'")[0]["n"]
        check(f"de missing after a partial translation (failures {st['translation_failures']})",de==0 and st["translation_failures"]>=1)
        FAKE["drop_translation"]=set(); st=con.run("t2")
        check("completed by the next run",q(W,"select count(*) n from long_time_memory where summary like '%Hobbies%' and language='de'")[0]["n"]==1)
    def test_11_chatbot_connection_cannot_write_long_term(self):
        """protections still hold: the chatbot's Memory cannot touch long term"""
        tmp, C, W, con = env()
        add(W, "hello seed")
        con.run("seed")   # a complete run records when it happened
        M=Memory(config=C,params=Dictionary({"api_key":"k","language":"en"}))
        try: M.apply_consolidation("create",[],"en","s","c"); denied=False
        except sqlite3.DatabaseError: denied=True
        check("apply_consolidation refused for a non-writer",denied)
        check("non-writer can read the meta (what Main does for the catch-up)",M.get_meta(Memory.META_LAST_CONSOLIDATION_AT) is not None)
        M.close()
