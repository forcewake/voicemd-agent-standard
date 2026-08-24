# MCP adapter

This optional server exposes:

- resource `voice://active`;
- tool `compile_voice_contract`;
- tool `lint_voice_output`.

```bash
python -m pip install -e '../..[mcp]'
python server.py
```

MCP makes the contract available to any compatible harness, but tool availability does not mean the voice contract can grant permissions. The host must still enforce the communication-only authority boundary.

The MCP Python API can evolve; pin the `mcp` package and test this adapter before deployment.
