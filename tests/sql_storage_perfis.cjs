const {PGlite}=require(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const fs=require('fs'),assert=require('node:assert/strict');
const sql=fs.readFileSync('migrations/storage_perfis_privado.sql','utf8');
(async()=>{
 for(const tipo of ['text','varchar(100)']) {
  const db=new PGlite();
  const exec=async s=>{try{return await db.exec(s);}catch(e){await db.exec('rollback;reset role;');throw e;}};
  try {
   await exec(`create role anon;create role authenticated;create role service_role bypassrls;
    create schema storage;
    create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
    create table storage.objects(id int primary key,bucket_id ${tipo},name text);
    alter table storage.objects enable row level security;
    grant usage on schema storage to anon,authenticated,service_role;
    grant all on storage.objects to anon,authenticated,service_role;
    create policy preexistente_ampla on storage.objects for all to public using(true) with check(true);
    insert into storage.objects values(1,'lifes-perfis','foto.png'),(2,'outro-bucket','outro.png');`);
   await exec(sql);await exec(sql);
   for(const papel of ['anon','authenticated']) {
    await exec(`set role ${papel};`);
    assert.deepEqual((await db.query('select id from storage.objects order by id')).rows,[{id:2}]);
    assert.equal((await db.query("delete from storage.objects where id=1 returning id")).rows.length,0);
    await assert.rejects(exec("insert into storage.objects values(3,'lifes-perfis','fraude');"),e=>e.code==='42501');
   }
   await exec('set role service_role;');assert.equal((await db.query('select * from storage.objects')).rows.length,2);await exec('reset role;');
   // Política homônima adulterada: aborta e não remove/substitui silenciosamente.
   await exec('alter policy lifes_perfis_somente_backend on storage.objects using(true);');
   await assert.rejects(exec(sql),/Política de fotos existente incompatível/);
   assert.equal((await db.query('select count(*) n from storage.objects')).rows[0].n,2);
  } finally {await db.close();}
 }
 console.log('Storage local OK: bucket privado, política restritiva, preservação, text/varchar, service_role e reexecução.');
})().catch(e=>{console.error(e);process.exitCode=1;});
