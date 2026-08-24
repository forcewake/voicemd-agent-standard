using VoiceMd;

using var http = new HttpClient { BaseAddress = new Uri("http://127.0.0.1:8765") };
var client = new VoiceMdClient(http);
var prompt = await client.CompileAsync(new VoiceSelector(Profile: "architecture_review"));
Console.WriteLine(prompt);
