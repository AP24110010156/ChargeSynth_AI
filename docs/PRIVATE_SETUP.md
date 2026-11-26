# Private developer setup

This file is for the person running the app. None of this configuration is shown in the product interface.

The dataset model and capacity comparison work immediately. Custom language interpretation uses the server-side service selected for this project. Without an available live response, the interface clearly labels a **Guided scenario** or **Calculated assessment**; it does not pretend those texts came from a live language model.

## Fresh installation

Open **ChargeSynth_AI/.env** in VS Code. It is in the project root, beside **run.py**, not in `frontend`, `backend` or `docs`.

```dotenv
GROQ_API_KEY=paste_your_key_here
GROQ_MODEL=openai/gpt-oss-120b
HOST=127.0.0.1
PORT=5000
OPEN_BROWSER=1
```

Replace the placeholder on the first line with your own Groq credential. Save, stop the running terminal with Ctrl+C, then restart. If `.env` is not present, copy `.env.example` to `.env`; the launcher also does this automatically. Do not place credentials in HTML or JavaScript or share a ZIP containing your filled `.env`.

The service endpoint is `https://api.groq.com/openai/v1/chat/completions`. The server sends the prompt and entered scenario controls for scenario interpretation, or calculated summary and planning assumptions for an explanation. It does not send the entire session table or read arbitrary files. The browser never receives the credential or service diagnostics. The model name can be changed here if your account offers a different compatible model. Account access and rate limits still apply.

The update was tested with mocked remote responses, malformed outputs, timeouts and authorization failures. No live credential was supplied for this release's end-to-end account test.

If a private configuration is not recognized, check that this is the folder you actually launched, restart after saving, and confirm that a separately defined operating-system environment variable is not overriding the file. `load_dotenv` intentionally does not override existing process environment variables.
