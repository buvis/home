import { command, readRecord } from "../revive/lib/core.js";

const labels = JSON.parse(process.argv[2]);
const record = readRecord(labels);
const argv = record && !record.needs.length ? command(record, "resume", { unattended: true }) : null;
process.stdout.write(JSON.stringify(argv));
