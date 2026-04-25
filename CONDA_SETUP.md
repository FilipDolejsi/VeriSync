"""
VeriSync Conda Environment Setup Guide
=====================================

Environment Name: verisync
Python Version: 3.11.15

Quick Start
-----------

1. Activate the environment:
   conda activate verisync

2. Deactivate the environment:
   conda deactivate

3. List conda environments:
   conda env list

4. Run the test script:
   conda run -n verisync python tests/test_llm_providers.py

Environment Details
-------------------

The 'verisync' conda environment includes all project dependencies:

LLM Providers:
- Groq API (v1.2.0) - for classifier_node using Llama 3
- Google Generative AI - for verifier_node and synthesiser_node using Gemini

Core Framework:
- LangGraph (1.1.9) - Graph-based state management
- LangChain (core) - LLM framework
- FastAPI (0.136.1) - Web framework

ML/AI Models:
- PyTorch (2.11.0) - Deep learning
- Transformers (5.6.2) - NLP models
- Sentence Transformers (5.4.1) - Embeddings
- scikit-learn (1.8.0) - ML algorithms

Database & Storage:
- aiosqlite (0.22.1) - Async SQLite
- pyyaml (6.0.3) - YAML parsing

GitHub Integration:
- PyGithub (2.9.1) - GitHub API
- authlib (1.7.0) - OAuth authentication

API & Utilities:
- httpx (0.28.1) - HTTP client with L402 support
- Pydantic (2.13.3) - Data validation
- Rich (15.0.0) - Terminal formatting

Testing:
- pytest (9.0.3) - Test framework
- pytest-asyncio (1.3.0) - Async test support

Environment Variables Required
-------------------------------

Create or update .env file with:

GROQ_API_KEY=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
GEMINI_API_KEY=AIzaSyB0vRzVKpWJypAxAN9XbkYyC3gPJijKaic

Running the Application
-----------------------

1. Activate environment:
   conda activate verisync

2. Start development server:
   conda run -n verisync python main.py

3. Or run directly in activated environment:
   conda activate verisync
   python main.py

Testing LLM Providers
---------------------

Run comprehensive tests for all LLM integrations:
   conda run -n verisync python tests/test_llm_providers.py

This will:
- Test all Groq models (Llama 3, Mistral, Gemma)
- Verify Gemini API connectivity
- Test classifier node with Groq
- Test verifier node with Gemini

Common Commands
---------------

# Check Python version in environment
conda run -n verisync python --version

# List installed packages
conda run -n verisync pip list

# Update a package
conda run -n verisync pip install --upgrade <package_name>

# Run Python script
conda run -n verisync python <script_path>

# Deactivate current environment
conda deactivate

Troubleshooting
---------------

If you encounter issues with the environment:

1. Update conda:
   conda update -n base -c defaults conda

2. Reactivate environment:
   conda deactivate
   conda activate verisync

3. Reinstall a specific package:
   conda run -n verisync pip install --force-reinstall <package_name>

4. Check environment info:
   conda info --envs

Location
--------
Environment path: C:\\Users\\user\\miniconda3\\envs\\verisync
"""
