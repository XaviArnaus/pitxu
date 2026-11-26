"""Database migrations, backups, preload and the protection of the long term memory."""
import os
import shutil
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403

P = params(language="es")
MIGRATIONS = sorted(f for f in os.listdir(os.path.join(REPO, "migrations/pitxu")) if f.endswith(".sql"))
LATEST = len(MIGRATIONS)   # the files are numbered 0001, 0002, ... so the schema version is how many there are
raises = raises_database_error


class StorageTests(unittest.TestCase):
    def test_01_upgrade_of_a_v1_database_preload_and_protection(self):
        """an existing v1 database with data + legacy language + preload (writer) + the chatbot side (NOT a long term writer)"""
        tmp = tempfile.mkdtemp()
        dbpath = tmp + "/db/pitxu.db"
        os.makedirs(tmp + "/db")
        con=sqlite3.connect(dbpath); con.executescript(read_file(os.path.join(REPO, "migrations/pitxu/0001_init.sql")))
        for i in range(3): con.execute("INSERT INTO short_time_memory(summary,content,created_at) VALUES(?,?,?)",(f"old {i}",f"content {i}","2026-05-0%dT10:00:00"%(i+1)))
        con.execute("INSERT INTO long_time_memory(summary,content) VALUES('legacy long','x')"); con.commit(); con.close()
        C=cfg(tmp); P=params(language="es")
        db=DbSqlite(config=C,params=P); n=db.migrate_db()
        check(f"applied every migration after the first: {n}",n==LATEST-1)
        check("user_version is the latest",db.connection.execute("pragma user_version").fetchone()[0]==LATEST)
        bk=os.listdir(tmp+"/db/backups"); check(f"a backup was made: {bk}",len(bk)==1 and "migration" in bk[0] and "v1" in bk[0])
        b=sqlite3.connect(tmp+"/db/backups/"+bk[0]); check("backup is the v1 data (3 short rows, version 1)",b.execute("select count(*) from short_time_memory").fetchone()[0]==3 and b.execute("pragma user_version").fetchone()[0]==1); b.close()
        r=db.connection.execute("select status,attempts,language from short_time_memory").fetchall()
        check("existing short rows: pending, 0 attempts, no language yet",all(x["status"]=="pending" and x["attempts"]==0 and x["language"] is None for x in r) and len(r)==3)
        check("existing long row became its own topic",db.connection.execute("select topic_id=id from long_time_memory").fetchone()[0]==1)
        check("journal mode is WAL",db.connection.execute("pragma journal_mode").fetchone()[0]=="wal")
        check("second run applies nothing and makes no new backup",db.migrate_db()==0 and len(os.listdir(tmp+"/db/backups"))==1)
        db.close()
        W=Memory(config=C,params=Dictionary({"api_key":"k","long_term_writer":True}))
        check("backfill sets 'en' on 3 short + 1 long",W.backfill_legacy_language()==4)
        check("backfill is idempotent",W.backfill_legacy_language()==0)
        W.preload_memory()
        rows=W.db.connection.execute("select preload_key,topic_id,language from long_time_memory where preload_key is not null").fetchall()
        check(f"preload wrote 3 topics x 4 languages = {len(rows)} rows",len(rows)==12)
        topics={}
        for x in rows: topics.setdefault(x["preload_key"],set()).add(x["topic_id"])
        check("each topic shares ONE topic_id across languages",all(len(v)==1 for v in topics.values()) and len(topics)==3)
        W.preload_memory(); check("preload twice writes nothing new",W.db.connection.execute("select count(*) from long_time_memory").fetchone()[0]==13)
        es=W.get_by_exact_summary(W.TABLE_LONG_TIME_MEMORY,"Vehículos - coche, moto, furgoneta")
        check("Spanish preload entry readable, tagged 'es'",es and es[0]["language"]=="es" and "Montesa" in es[0]["content"])
        W.db.connection.execute("delete from long_time_memory where preload_key='vehicles' and language='de'"); W.db.connection.commit()
        W.preload_memory(); check("a language removed from the DB is re-created, not the rest",W.db.connection.execute("select count(*) from long_time_memory where preload_key='vehicles'").fetchone()[0]==4)
        dup=raises(lambda:W.create_long_memory_entry("a","b","en",topic_id=W.get_long_memory_by_preload_key("vehicles")[0]["topic_id"]))
        check("unique (topic_id, language) rejects a duplicate version",dup is not None)
        W.close()
        M=Memory(config=C,params=Dictionary({"api_key":"k","language":"es"}))
        e=M.create_short_memory_entry("nuevo","algo"); check(f"short entry stamped with the session language: {e['language']}",e["language"]=="es")
        e2=M.create_short_memory_entry("new","something",language="de"); check("explicit language wins",e2["language"]=="de")
        check("update short works",M.update_short_memory_entry_by_id(e["id"],content="otra cosa")["content"]=="otra cosa")
        check("read long works",M.get_by_summary_like(M.TABLE_LONG_TIME_MEMORY,"vehic") is not None)
        for label,fn in [("insert",lambda:M.create_memory_entry(M.TABLE_LONG_TIME_MEMORY,"s","c")),
                         ("create_long_memory_entry",lambda:M.create_long_memory_entry("s","c","en")),
                         ("update",lambda:M.update_by_id(M.TABLE_LONG_TIME_MEMORY,1,summary="hacked")),
                         ("raw delete",lambda:M.db.connection.execute("delete from long_time_memory")),
                         ("drop",lambda:M.db.connection.execute("drop table long_time_memory"))]:
            msg=raises(fn); check(f"long term {label} is refused by the database ({msg})",msg is not None and "not authorized" in msg)
        check("long term data untouched",M.db.connection.execute("select count(*) from long_time_memory").fetchone()[0]==13)
        check("last entries: newest first, by id",M.get_last_short_memory_entries(2)[0]["id"]>M.get_last_short_memory_entries(2)[1]["id"])
        check("by date works",len(M.get_short_memory_by_date("2026-05-02"))==1)
        check("not found -> None (old contract)",M.get_short_memory_by_summary_like("zzz") is None and M.get_short_memory_by_exact_summary("zzz") is None)
        check("returned entries carry language, not internals",set(e.keys())=={"id","summary","content","created_at","language"})
        pid=M.create_pending_conversation([{"role":"user","text":"Adéu à tu"}],language="ca"); M.increment_pending_conversation_attempts(pid)
        p=M.get_pending_conversations(); check("pending conversation kept raw (accents intact), attempts 1",p[0]["history"][0]["text"]=="Adéu à tu" and p[0]["attempts"]==1 and p[0]["language"]=="ca")
        M.delete_pending_conversation(pid); check("pending conversation deleted",M.get_pending_conversations()==[])
        M.close()
    def test_02_empty_database(self):
        """empty DB: last entry is None, not a crash"""
        tmp2=tempfile.mkdtemp(); C2=cfg(tmp2); d2=DbSqlite(config=C2,params=P); check("fresh DB applies every migration",d2.migrate_db()==LATEST)
        check("fresh DB: no backup (nothing to lose)",not os.path.exists(tmp2+"/db/backups") or os.listdir(tmp2+"/db/backups")==[]); d2.close()
        M2=Memory(config=C2,params=Dictionary({"api_key":"k"})); check("get_last_short_memory_entry() on empty -> None",M2.get_last_short_memory_entry() is None)
        check("no session language -> app default (ca)",M2.create_short_memory_entry("a","b")["language"]=="ca"); M2.close()
    def test_03_failing_migration_is_rolled_back(self):
        """a failing migration is rolled back completely"""
        tmp3=tempfile.mkdtemp(); mig=tmp3+"/mig/"; os.makedirs(mig)
        for f in MIGRATIONS: shutil.copy(os.path.join(REPO, "migrations/pitxu/", f), mig + f)
        write_file(mig+"%04d_bad.sql" % (LATEST + 1),"BEGIN;\nALTER TABLE short_time_memory ADD COLUMN zz TEXT;\nINSERT INTO nonexistent VALUES(1);\nPRAGMA user_version = %d;\nCOMMIT;\n" % (LATEST + 1))
        write_file(mig+".keep","")   # not a migration: must be ignored
        C3=cfg(tmp3,**{"database.sqlite.migrations_path":mig}); d3=DbSqlite(config=C3,params=P)
        try: d3.migrate_db(); raised=False
        except Exception: raised=True
        cols=[r[1] for r in d3.connection.execute("pragma table_info(short_time_memory)")]
        check("error raised",raised); check("column from the failed migration is gone",("zz" not in cols))
        check("still at the latest good version",d3.connection.execute("pragma user_version").fetchone()[0]==LATEST)
        check("the .keep file was ignored, v2 data layer intact","status" in cols); d3.close()
    def test_04_backup_retention(self):
        """backup retention"""
        tmp4=tempfile.mkdtemp(); C4=cfg(tmp4,**{"database.sqlite.backups_keep":2}); d4=DbSqlite(config=C4,params=P); d4.migrate_db()
        import time
        for i in range(4): d4.backup_db(f"t{i}"); time.sleep(0.05)
        left=sorted(os.listdir(tmp4+"/db/backups")); check(f"only the newest 2 are kept: {left}",len(left)==2 and "t3" in left[-1] and "t2" in left[0]); d4.close()
