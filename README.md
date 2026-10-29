# Boggle Algorithm Benchmark

This is a small Python and Streamlit app that compares six ways to solve a 4x4
Boggle board:

- brute-force DFS
- prefix-set DFS
- trie DFS
- dictionary-driven DFS
- frequency-filtered trie DFS
- trie DFS with subtree pruning

## Run

Use Python 3.10 or newer:

```powershell
python -m pip install -r requirements.txt
streamlit run server.py
```

Streamlit opens the app in a browser. Enter four rows of four letters, choose
the minimum word length, and optionally upload a text dictionary.

The bundled dictionary is in `data/default_dictionary.txt`. Each line is
normalized to uppercase; blank, non-ASCII, and non-letter lines are rejected.
