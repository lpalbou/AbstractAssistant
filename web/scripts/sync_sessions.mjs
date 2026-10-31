// Generated UI is owned by AbstractUIC; normal builds verify the pinned snapshot.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
const root=fileURLToPath(new URL("../",import.meta.url));
const target=resolve(root,"src/vendor/abstractsessions");
if(process.argv.includes("--check")) {
 const m=JSON.parse(readFileSync(resolve(target,"provenance.json"),"utf8"));
 const allowed=["session_cards.js","session_cards.css","session_cards.d.ts","session_card.d.ts","session_activity.d.ts","session_reads.d.ts","session_read_client.d.ts","automation_card.d.ts","automation_panel.js","automation_panel.d.ts"];
 if(m.schema_version!==1 || m.owner!=="@abstractframework/ui-kit" || Object.keys(m.artifacts).length!==allowed.length) throw new Error("Unsupported session snapshot");
 for(const name of allowed) if(createHash("sha256").update(readFileSync(resolve(target,name))).digest("hex")!==m.artifacts[name]) throw new Error(`Changed shared session artifact: ${name}`);
 console.log("Shared session snapshot integrity verified");
} else {
 const result=spawnSync(process.execPath,[resolve(root,"../../abstractuic/ui-kit/scripts/export_session_cards.mjs"),"--out",target],{stdio:"inherit"});
 if(result.status!==0) process.exit(result.status || 1);
}
