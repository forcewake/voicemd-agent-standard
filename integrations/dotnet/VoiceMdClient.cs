using System.Net.Http.Json;
using System.Text.Json.Serialization;

namespace VoiceMd;

public sealed record VoiceSelector(
    string? Profile = null,
    string? Audience = null,
    string? Surface = null,
    string? Tone = null,
    string? Format = null,
    bool? Compact = null,
    int? MaxChars = null);

public sealed record LintIssue(
    [property: JsonPropertyName("rule_id")] string RuleId,
    string Severity,
    string Message,
    string? Evidence);

public sealed record LintResult(bool Ok, IReadOnlyList<LintIssue> Issues);

public sealed class VoiceMdClient(HttpClient httpClient)
{
    public async Task<string> CompileAsync(VoiceSelector? selector = null, CancellationToken cancellationToken = default)
    {
        selector ??= new VoiceSelector();
        var query = new List<string>();
        Add(query, "profile", selector.Profile);
        Add(query, "audience", selector.Audience);
        Add(query, "surface", selector.Surface);
        Add(query, "tone", selector.Tone);
        Add(query, "format", selector.Format);
        Add(query, "compact", selector.Compact?.ToString().ToLowerInvariant());
        Add(query, "max_chars", selector.MaxChars?.ToString());

        var path = "/v1/voice/prompt" + (query.Count == 0 ? "" : "?" + string.Join("&", query));
        using var response = await httpClient.GetAsync(path, cancellationToken);
        response.EnsureSuccessStatusCode();
        var payload = await response.Content.ReadFromJsonAsync<CompileResponse>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("VoiceMD returned an empty response.");
        return payload.Prompt;
    }

    public async Task<LintResult> LintAsync(
        string text,
        VoiceSelector? selector = null,
        CancellationToken cancellationToken = default)
    {
        selector ??= new VoiceSelector();
        using var response = await httpClient.PostAsJsonAsync(
            "/v1/voice/lint",
            new
            {
                text,
                profile = selector.Profile,
                audience = selector.Audience,
                surface = selector.Surface,
                tone = selector.Tone
            },
            cancellationToken);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<LintResult>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("VoiceMD returned an empty response.");
    }

    private static void Add(List<string> query, string name, string? value)
    {
        if (!string.IsNullOrWhiteSpace(value))
            query.Add($"{Uri.EscapeDataString(name)}={Uri.EscapeDataString(value)}");
    }

    private sealed record CompileResponse(string Prompt);
}
