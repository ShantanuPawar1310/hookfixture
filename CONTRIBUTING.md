# Contributing

HookFixture is early-stage. Small, reproducible improvements are welcome.

1. Open an issue describing a real handler-testing problem, or choose an existing
   issue. Use synthetic events and explain the expected result.
2. Fork the repository and create a branch for the change.
3. Install with `python -m pip install -e .` in a virtual environment.
4. Add a regression test when behavior changes. Run
   `python -m unittest discover -s tests -v` and the consumer example.
5. Update the format documentation or README if the public behavior changes.
6. Open a pull request explaining the problem, the behavior after the change,
   and how you tested it.

Keep the core dependency-free and deterministic. Do not add network delivery,
credentials, telemetry or provider-specific assumptions to the generic envelope.
Discuss new runtime dependencies and format changes before implementation.

Do not commit customer data, tokens, production webhook payloads or copied code
without appropriate permissions and attribution. New code contributions are made
under this repository's MIT License. Be respectful and focus reviews on the work.
