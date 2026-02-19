Local SLM for Strategy Tools (SandiBot)
=======================================

Place your GGUF model file here so the app can run fully offline.

1. Copy a GGUF model file into this folder and name it model.gguf
   (or set the "Model path" in the Strategy Tools section to your file path).

2. Recommended: small instruct models (e.g. 1–3B parameters) for fast CPU inference
   on Windows, e.g.:
   - TinyLlama, Phi-2, or similar GGUF variants from Hugging Face.

3. The app uses this model only for:
   - Draft follow-up emails
   - Strategy summary (bullets)
   - Call agenda (timeboxed)

   All content is grounded by the Knowledge Graph; the model does not call any
   external APIs or servers.

4. Do NOT commit the model file to GitHub unless you intend to; keep it local
   or add models/slm/*.gguf to .gitignore.

5. To run fully offline: install dependencies (pip install -r requirements.txt),
   then start the Streamlit app. No Ollama or llama.cpp server is required;
   the model loads inside the Python process.
