import { writeFileSync, existsSync } from 'node:fs';
import { isAbsolute } from 'node:path';
import { openStore, provision, putAlias, hash } from './store.mjs';

const [command, ...args] = process.argv.slice(2);
if (!process.env.MAD_DATABASE || !isAbsolute(process.env.MAD_DATABASE)) throw new Error('set MAD_DATABASE to an absolute path');
const db = openStore(process.env.MAD_DATABASE);
try {
  if (command === 'create-vault' || command === 'add-device') {
    const [output, vault, label] = args;
    if (!output || (command === 'add-device' && !vault)) throw new Error('usage: create-vault output.json | add-device output.json vault label');
    if (existsSync(output)) throw new Error('output already exists');
    const record = provision(db, command === 'add-device' ? vault : null, label);
    try {
      writeFileSync(output, JSON.stringify(record, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
    } catch (error) {
      db.prepare('DELETE FROM tokens WHERE hash=?').run(hash(record.token));
      if (command === 'create-vault') db.prepare('DELETE FROM vaults WHERE id=?').run(record.vault);
      throw error;
    }
    console.log('credentials saved; keep this file private');
  } else if (command === 'alias') {
    putAlias(db, args[0] ?? '', args[1] ?? '', Number(args[2] ?? 0));
    console.log('alias saved');
  } else if (command === 'remove-alias') {
    db.prepare('DELETE FROM aliases WHERE alias=?').run((args[0] ?? '').replace(/^@/, '').toLowerCase());
  } else if (command === 'devices') {
    console.log(JSON.stringify(db.prepare('SELECT hash,vault,label FROM tokens WHERE vault=?').all(args[0]), null, 2));
  } else if (command === 'revoke-device') {
    db.prepare('DELETE FROM tokens WHERE hash=?').run(args[0]);
  } else {
    throw new Error('commands: create-vault, add-device, alias, remove-alias, devices, revoke-device');
  }
} finally { db.close(); }
