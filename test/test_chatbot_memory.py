"""What the chatbot reads and edits: S:/L: ids, search over both memories, corrections and forget requests."""
import os
import shutil
import sys
import threading
import time
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403

class ChatbotMemoryTests(unittest.TestCase):
    def setUp(self):
        self._real_llm = Memory.request_llm_json
        Memory.request_llm_json = fake_llm
        reset_fake()

    def tearDown(self):
        Memory.request_llm_json = self._real_llm

    def test_01_ids_and_search_in_both_memories(self):
        """ids, refs and presentation + search: both memories, short first, in the session language"""
        tmp,C,W,con=env()
        P=Memory.parse_ref
        check("parse refs",P("S:12")==("S",12) and P("l:5")==("L",5) and P("12")==("S",12) and P(7)==("S",7) and P("x")is None and P("L:")is None and P("S:1;drop")is None)
        T=tools(C); e=T.create_memory_entry("New dog","Rex is the dog")
        check(f"create returns a prefixed id: {e['id']}",str(e["id"]).startswith("S:") and "topic_id" not in e and "status" not in e)
        add(W,"Vehicles pending news","a pending note")  # short, pending
        r=T.get_memory_entries_by_summary("vehicles")
        ids=[x["id"] for x in r]
        check(f"short first then long: {ids}", ids[0].startswith("S:") and any(i.startswith("L:") for i in ids) and ids.index(next(i for i in ids if i.startswith("L:")))>0)
        check("exactly one long version of the vehicles topic, in english",len([x for x in r if x["id"].startswith("L:")])==1 and all(x["language"]=="en" for x in r if x["id"].startswith("L:")))
        Tes=tools(C,"es"); r=Tes.get_memory_entries_by_summary("vehicles")  # english word, spanish session
        l=[x for x in r if x["id"].startswith("L:")]
        check(f"english query in a spanish session returns the spanish version: {[x['language'] for x in l]}",len(l)==1 and l[0]["language"]=="es")
        Tca=tools(C,"ca"); l=[x for x in Tca.get_memory_entries_by_summary("vehicles") if x["id"].startswith("L:")]
        check("same for catalan",len(l)==1 and l[0]["language"]=="ca")
        r=T.get_memory_entries_by_summary("no-such-thing-xyz"); check("not found stays a message (str)",isinstance(r,str))
    def test_02_no_duplicates_after_consolidation(self):
        """no duplicates after consolidation, pending ones always show"""
        tmp, C, W, con = env()
        T = tools(C)
        s1=add(W,"vehicles: sold montesa","c"); con.run("x")
        r=T.get_memory_entries_by_summary("vehicles")
        check(f"consolidated short entry hidden when its topic is in the results: {[x['id'] for x in r]}",not any(x["summary"]=="vehicles: sold montesa" for x in r) and any(x["id"].startswith("L:") for x in r))
        p=add(W,"vehicles pending again","c")
        r=T.get_memory_entries_by_summary("vehicles")
        check("a pending short entry shows next to the long topic, first",r[0]["summary"]=="vehicles pending again" and any(x["id"].startswith("L:") for x in r))
        # a stale version is never returned
        topic=q(W,"select topic_id from long_time_memory where preload_key='vehicles' limit 1")[0]["topic_id"]
        W.db.connection.execute("update long_time_memory set stale=1 where topic_id=? and language='en'",(topic,)); W.db.connection.commit()
        r=T.get_memory_entries_by_summary("vehicles"); l=[x for x in r if x["id"].startswith("L:")]
        check(f"stale english version skipped, falls back to another language: {[x['language'] for x in l]}",len(l)==1 and l[0]["language"]!="en")
        W.db.connection.execute("update long_time_memory set stale=0 where topic_id=?",(topic,)); W.db.connection.commit()
    def test_03_date_last_five_and_by_id(self):
        """date and last five and by id"""
        tmp, C, W, con = env()
        T = tools(C)
        e = T.create_memory_entry("New dog", "Rex is the dog")
        d=datetime.now().strftime("%Y-%m-%d"); r=T.get_memory_entries_by_date(d)
        check("by date: prefixed ids from short",isinstance(r,list) and all(":" in x["id"] for x in r) and any(x["id"].startswith("S:") for x in r))
        r=T.get_last_five_memory_entries(); check("last five: short only, S: ids",isinstance(r,list) and len(r)<=5 and all(x["id"].startswith("S:") for x in r))
        lid=[x for x in T.get_memory_entries_by_summary("vehicles") if x["id"].startswith("L:")][0]["id"]
        check("get by id L:",T.get_memory_entry_by_id(lid)["id"]==lid)
        check("get by id S:",T.get_memory_entry_by_id(e["id"])["summary"]=="New dog")
        check("get by id: wrong format and unknown are messages",isinstance(T.get_memory_entry_by_id("zzz"),str) and isinstance(T.get_memory_entry_by_id("L:999999"),str))
    def test_04_update_short_and_correct_long_term(self):
        """update: S: in place, L: becomes a correction + the consolidator applies the correction to the topic (fake LLM follows the correction text)"""
        tmp, C, W, con = env()
        T = tools(C)
        e = T.create_memory_entry("New dog", "Rex is the dog")
        lid = [x for x in T.get_memory_entries_by_summary("vehicles") if x["id"].startswith("L:")][0]["id"]
        r=T.update_memory_entry_by_id(e["id"],summary="New dog",content="Rex, a labrador"); check("S: updated in place",r["content"]=="Rex, a labrador" and "note" not in r)
        before=q(W,"select content from long_time_memory where id=?",int(lid.split(":")[1]))[0]["content"]
        r=T.update_memory_entry_by_id(lid,summary="Vehicles: sold the Montesa",content="The Montesa was sold.")
        check(f"L: update -> new short pending entry with a note: {r.get('id')}",isinstance(r,dict) and r["id"].startswith("S:") and "note" in r and "Correction to the long term memory topic" in r["content"])
        check("long term row untouched",q(W,"select content from long_time_memory where id=?",int(lid.split(':')[1]))[0]["content"]==before)
        lv=[x for x in T.get_memory_entries_by_summary("vehicles") if x["id"].startswith("L:")][0]
        check(f"the long entry points to the pending correction: {lv.get('pending_correction')}",lv.get("pending_correction")==r["id"])
        check("the correction is linked to its topic in the db",q(W,"select topic_id from short_time_memory where id=?",int(r["id"][2:]))[0]["topic_id"]==q(W,"select topic_id from long_time_memory where id=?",int(lid[2:]))[0]["topic_id"])
        check("the correction is searchable right away and comes first",T.get_memory_entries_by_summary("vehicles")[0]["id"]==r["id"])
        check("L: update with a missing field is refused",isinstance(T.update_memory_entry_by_id(lid,summary="x"),str))
        check("bad id is a message",isinstance(T.update_memory_entry_by_id("nonsense",summary="a",content="b"),str))
        corr=r["id"]
        orig=fake_llm
        def fake2(self,prompt,schema,model=None,settings="summarization",purpose="summarization"):
            if purpose=="memory consolidation":
                data=json.loads(prompt.rsplit("# Input\n",1)[1]); ops=[]
                assert "correction_of_topic" in prompt   # the hint and rule 9 are in the prompt
                for en in data["pending_entries"]:
                    if en.get("correction_of_topic") is not None:
                        t=next(t for t in data["existing_topics"] if t["topic_id"]==en["correction_of_topic"])
                        ops.append({"action":"update","topic_id":t["topic_id"],"source_ids":[en["id"]],"language":data["language"],"summary":t["summary"],"content":"CORRECTED: "+en["content"].split("\n")[0]})
                    else: ops.append({"action":"ignore","source_ids":[en["id"]]})
                return json.dumps({"operations":ops})
            return orig(self,prompt,schema,model,settings,purpose)
        Memory.request_llm_json=fake2
        con.run("corr"); Memory.request_llm_json=orig
        veh=q(W,"select language,content from long_time_memory where preload_key='vehicles'")
        check(f"topic corrected in en and translated: {[ (v['language'],v['content'][:22]) for v in veh]}",all("CORRECTED" in v["content"] for v in veh) and len(veh)==4)
        check("the correction is consolidated and hidden behind its topic",not any(x["id"]==corr for x in T.get_memory_entries_by_summary("vehicles")) and any(x["id"].startswith("L:") for x in T.get_memory_entries_by_summary("vehicles")))

        check("after consolidation the flag is gone",not any(x.get("pending_correction") for x in T.get_memory_entries_by_summary("vehicles")))
    def test_05_correction_with_many_topics_is_a_candidate(self):
        """the linked topic is a candidate even when there are many topics"""
        orig = fake_llm
        tmp2,C2,W2,con2=env(**{"memory.consolidation.max_candidates":1})
        Tt=tools(C2); lid2=[x for x in Tt.get_memory_entries_by_summary("vehicles") if x["id"].startswith("L:")][0]["id"]
        Tt.update_memory_entry_by_id(lid2,summary="Vehicles fixed",content="completely unrelated words zzz")
        seen={}
        def spy2(self,prompt,schema,model=None,settings="summarization",purpose="summarization"):
            if purpose=="memory consolidation": seen["d"]=json.loads(prompt.rsplit("# Input\n",1)[1])
            return orig(self,prompt,schema,model,settings,purpose)
        Memory.request_llm_json=spy2; con2.run("many"); Memory.request_llm_json=orig
        d=seen["d"]; tid=q(W2,"select topic_id from long_time_memory where id=?",int(lid2[2:]))[0]["topic_id"]
        check(f"candidate list has the linked topic and the entry carries the hint: {[t['topic_id'] for t in d['existing_topics']]}",
              d["existing_topics"][0]["topic_id"]==tid and d["pending_entries"][0].get("correction_of_topic")==tid)
    def test_06_forget_requests(self):
        """forget"""
        tmp, C, W, con = env()
        T = tools(C)
        n=T.create_memory_entry("temp note","delete me"); r=T.forget_memory_entry(n["id"])
        check("S: not in long term: deleted",r["note"]==T._message("short_entry_deleted") and q(W,"select 1 from short_time_memory where id=?",int(n["id"][2:]))==[])
        lid=[x for x in T.get_memory_entries_by_summary("vehicles") if x["id"].startswith("L:")][0]["id"]
        lrow=lambda: q(W,"select id,summary,content from long_time_memory order by id")
        snap=lrow()
        r=T.forget_memory_entry(lid)
        check(f"L: forget registers a request, nothing is deleted: {r['summary'][:50]}",r["summary"].startswith(Memory.FORGET_REQUEST_PREFIX) and "note" in r and lrow()==snap)
        r2=T.forget_memory_entry(lid); check("a second request does not duplicate",r2["id"]==r["id"] and q(W,"select count(*) n from short_time_memory where summary like 'FORGET REQUEST%'")[0]["n"]==1)
        res=T.get_memory_entries_by_summary("vehicles"); L=[x for x in res if x["id"].startswith("L:")][0]
        check(f"the long entry carries forget_requested_on: {L.get('forget_requested_on')}",L.get("forget_requested_on")==datetime.now().strftime("%Y-%m-%d"))
        check("the forget request is hidden behind the topic (not repeated)",not any(x["summary"].startswith("FORGET") for x in res))
        Tes2=tools(C,"es"); L=[x for x in Tes2.get_memory_entries_by_summary("vehicles") if x["id"].startswith("L:")][0]
        check("also visible from a spanish session (the topic is the same)",L.get("forget_requested_on") is not None and L["language"]=="es")
        fid=r["id"]
        check("a forget request cannot be edited nor forgotten by the chatbot",isinstance(T.update_memory_entry_by_id(fid,summary="a",content="b"),str) and isinstance(T.forget_memory_entry(fid),str))
        con.run("after-forget"); st=q(W,"select status from short_time_memory where id=?",int(fid[2:]))[0]["status"]
        check("the consolidator never takes it",st=="ignored")
        W.db.connection.execute("update short_time_memory set consolidated_at=? where id=?",((datetime.now()-timedelta(days=400)).isoformat(),int(fid[2:]))); W.db.connection.commit()
        W.prune_short_memory(14); check("pruning never deletes it, however old",q(W,"select 1 from short_time_memory where id=?",int(fid[2:]))!=[])
        # forgetting a consolidated short entry = forgetting its topic
        s2=add(W,"vehicles: sold honda","c"); con.run("c2")
        sid="S:%d"%s2; r=T.forget_memory_entry(sid)
        check("forgetting a consolidated S: entry registers the forget of its topic",r["summary"].startswith(Memory.FORGET_REQUEST_PREFIX) and q(W,"select 1 from short_time_memory where id=?",s2)!=[])
    def test_07_write_protection(self):
        """the chatbot connection still cannot write the long term memory"""
        tmp, C, W, con = env()
        try: W2=Memory(config=C,params=Dictionary({"api_key":"k","language":"en"})); W2.db.connection.execute("update long_time_memory set content='x'"); denied=False
        except sqlite3.DatabaseError: denied=True
        check("write protection holds",denied)


class SearchTests(unittest.TestCase):
    """ The search by keywords over both memories: natural queries must find the long term entries too. """

    def setUp(self):
        self.tmp, self.config, self.writer, self.consolidator = env()
        self.tools = tools(self.config)

    def _ids(self, query):
        result = self.tools.get_memory_entries_by_summary(query)
        return [entry["id"] for entry in result] if isinstance(result, list) else []

    def _long_vehicles(self):
        return [x["id"] for x in self.tools.get_memory_entries_by_summary("vehicles") if x["id"].startswith("L:")][0]

    def test_natural_queries_find_the_long_term_entry(self):
        vehicles = self._long_vehicles()
        for query in ["vehicles", "moto", "Montesa",              # the title, a word of the title, a word only in the content
                      "vehicles moto", "what vehicles do I have",   # several words, a whole question
                      "blue hatchback", "Vehículos", "vehiculos"]:   # content only, accents
            self.assertIn(vehicles, self._ids(query), query)

    def test_a_synonym_that_is_nowhere_finds_nothing(self):
        self.assertEqual(self._ids("motorbike"), [])
        self.assertIsInstance(self.tools.get_memory_entries_by_summary("motorbike"), str)

    def test_nothing_to_search_for_finds_nothing(self):
        self.assertEqual(self._ids("do it"), [])     # only stop words and short words, and no entry has that text
        self.assertEqual(self._ids("   "), [])

    def test_the_content_of_short_term_entries_is_searched_too(self):
        entry = self.tools.create_memory_entry("Trip plans", "We go to Altafulla in August")
        self.assertIn(entry["id"], self._ids("Altafulla"))

    def test_the_best_matches_come_first_and_the_short_term_wins_ties(self):
        short = self.tools.create_memory_entry("Montesa vehicles", "the moto")
        ids = self._ids("Montesa vehicles")
        self.assertEqual(ids[0], short["id"])
        self.assertTrue(any(i.startswith("L:") for i in ids))
        self.assertLess(ids.index(short["id"]), [i for i in range(len(ids)) if ids[i].startswith("L:")][0])

    def test_the_results_are_limited(self):
        for number in range(12):
            self.tools.create_memory_entry(f"Dog walk {number}", "the dog needs a walk")
        self.assertEqual(len(self._ids("dog walk")), 8)
        _, limited_config, _, _ = env(**{"memory.search.max_results": 3})
        limited = tools(limited_config)
        for number in range(6):
            limited.create_memory_entry(f"Cat nap {number}", "the cat sleeps")
        self.assertEqual(len(limited.get_memory_entries_by_summary("cat")), 3)

    def test_the_relevant_long_term_entry_is_not_cut_by_many_weak_short_term_ones(self):
        for number in range(12):
            self.tools.create_memory_entry(f"Note {number}", "something about a moto")
        ids = self._ids("vehicles moto")
        self.assertIn(self._long_vehicles(), ids)

    def test_a_consolidated_entry_is_still_not_repeated(self):
        add(self.writer, "vehicles: sold montesa", "c")
        real = Memory.request_llm_json
        Memory.request_llm_json = fake_llm
        try:
            self.consolidator.run("test")
        finally:
            Memory.request_llm_json = real
        result = self.tools.get_memory_entries_by_summary("vehicles montesa")
        self.assertFalse(any(entry["summary"] == "vehicles: sold montesa" for entry in result))
