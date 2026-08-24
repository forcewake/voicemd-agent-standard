export type VoiceSelector = {
  profile?: string;
  audience?: string;
  surface?: string;
  tone?: string;
  format?: "prompt" | "json" | "ascii" | "nemotron" | "nemotron-ascii";
  compact?: boolean;
  maxChars?: number;
};

export type LintIssue = {
  rule_id: string;
  severity: "info" | "warning" | "error" | string;
  message: string;
  evidence?: string | null;
};

export class VoiceMdClient {
  constructor(private readonly baseUrl = "http://127.0.0.1:8765") {}

  async compile(selector: VoiceSelector = {}): Promise<string> {
    const url = new URL("/v1/voice/prompt", this.baseUrl);
    if (selector.profile) url.searchParams.set("profile", selector.profile);
    if (selector.audience) url.searchParams.set("audience", selector.audience);
    if (selector.surface) url.searchParams.set("surface", selector.surface);
    if (selector.tone) url.searchParams.set("tone", selector.tone);
    if (selector.format) url.searchParams.set("format", selector.format);
    if (selector.compact !== undefined) url.searchParams.set("compact", String(selector.compact));
    if (selector.maxChars !== undefined) url.searchParams.set("max_chars", String(selector.maxChars));

    const response = await fetch(url);
    if (!response.ok) throw new Error(`VoiceMD compile failed: ${response.status} ${await response.text()}`);
    const payload = (await response.json()) as { prompt: string };
    return payload.prompt;
  }

  async lint(text: string, selector: VoiceSelector = {}): Promise<{ ok: boolean; issues: LintIssue[] }> {
    const response = await fetch(new URL("/v1/voice/lint", this.baseUrl), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        text,
        profile: selector.profile,
        audience: selector.audience,
        surface: selector.surface,
        tone: selector.tone,
      }),
    });
    if (!response.ok) throw new Error(`VoiceMD lint failed: ${response.status} ${await response.text()}`);
    return (await response.json()) as { ok: boolean; issues: LintIssue[] };
  }
}
