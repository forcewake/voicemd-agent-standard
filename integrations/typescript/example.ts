import { VoiceMdClient } from "./voicemd-client.js";

const client = new VoiceMdClient(process.env.VOICEMD_URL);
const voice = await client.compile({ profile: "executive_brief" });

const messages = [
  { role: "system", content: "You are the strategy analysis agent." },
  { role: "system", content: voice },
  { role: "user", content: "Summarize the decision." },
];

console.log(messages);
