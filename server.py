"""Small Streamlit app for comparing Boggle search strategies."""

from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable

import pandas as pd
import streamlit as st


SIZE = 4
ROOT = Path(__file__).parent
DEFAULT_FILE = ROOT / "data" / "default_dictionary.txt"
ALGORITHM_INFO = {
    "Brute-force DFS": (
        "Explores every possible board path up to the longest candidate word.",
        "O(N x B^L), approximately O(16 x 8^16) worst case.",
    ),
    "Prefix-set DFS": (
        "Stops a path when its letters are not a prefix in the dictionary.",
        "Preprocessing O(S); search O(N x B^L x L) worst case.",
    ),
    "Trie DFS": (
        "Uses trie branches instead of strings to check valid prefixes.",
        "Preprocessing O(S); search O(N x B^L) worst case.",
    ),
    "Trie DFS with subtree pruning": (
        "Stops trie branches after all words below them have been found.",
        "Preprocessing O(S); O(N x B^L + W x L) worst case.",
    ),
}


@dataclass
class Result:
    name: str
    words: dict[str, list[tuple[int, int]]]
    prep: float
    search: float
    states: int
    checks: int
    pruned: int


class Trie:
    def __init__(self) -> None:
        self.children: dict[str, Trie] = {}
        self.word: str | None = None
        self.left = 0

    def add(self, word: str) -> None:
        node = self
        node.left += 1
        for char in word:
            node = node.children.setdefault(char, Trie())
            node.left += 1
        node.word = word


def words_from(lines: list[str]) -> tuple[set[str], int]:
    words, rejected = set(), 0
    for line in lines:
        word = line.strip()
        if word and word.isascii() and word.isalpha():
            words.add(word.upper())
        else:
            rejected += 1
    return words, rejected


def board_from(text: str) -> list[list[str]]:
    rows = text.splitlines()
    if len(rows) != SIZE:
        raise ValueError("Board must contain exactly 4 rows.")
    board = [list(row.strip().upper()) for row in rows]
    if any(len(row) != SIZE or not "".join(row).isalpha() for row in board):
        raise ValueError("Each board row must contain exactly 4 letters.")
    return board


def neighbors() -> dict[int, list[int]]:
    result = {}
    for r in range(SIZE):
        for c in range(SIZE):
            i = r * SIZE + c
            result[i] = [
                (r + dr) * SIZE + c + dc
                for dr in (-1, 0, 1)
                for dc in (-1, 0, 1)
                if (dr or dc)
                and 0 <= r + dr < SIZE
                and 0 <= c + dc < SIZE
            ]
    return result


def path(cells: list[int]) -> list[tuple[int, int]]:
    return [(i // SIZE, i % SIZE) for i in cells]


def make_trie(words: set[str]) -> Trie:
    trie = Trie()
    for word in words:
        trie.add(word)
    return trie


def run(
    name: str,
    board: list[list[str]],
    dictionary: set[str],
    minimum: int,
    search: Callable[..., tuple[dict[str, list[tuple[int, int]]], int, int, int]],
) -> Result:
    prep = perf_counter()
    candidates = {w for w in dictionary if minimum <= len(w) <= 16}
    chars = sum(board, [])
    prep_seconds = perf_counter() - prep
    start = perf_counter()
    words, states, checks, pruned = search(chars, candidates, neighbors())
    return Result(name, words, prep_seconds, perf_counter() - start, states, checks, pruned)


def brute(chars, candidates, adjacent):
    found, states, checks, pruned = {}, 0, 0, 0
    longest = max(map(len, candidates), default=0)

    def dfs(i, used, cells, text):
        nonlocal states, checks, pruned
        states += 1
        if text in candidates:
            found.setdefault(text, path(cells))
        if len(text) == longest:
            return
        for nxt in adjacent[i]:
            checks += 1
            if used & 1 << nxt:
                pruned += 1
                continue
            dfs(nxt, used | 1 << nxt, cells + [nxt], text + chars[nxt])

    for i in range(16):
        dfs(i, 1 << i, [i], chars[i])
    return found, states, checks, pruned


def prefix(chars, candidates, adjacent):
    prefixes = {word[:i] for word in candidates for i in range(1, len(word) + 1)}
    return trie_search(chars, candidates, adjacent, prefixes)


def trie_search(chars, candidates, adjacent, prefixes=None):
    found, states, checks, pruned = {}, 0, 0, 0
    trie = make_trie(candidates) if prefixes is None else None

    def dfs(i, used, cells, text, node=None):
        nonlocal states, checks, pruned
        states += 1
        if text in candidates:
            found.setdefault(text, path(cells))
        for nxt in adjacent[i]:
            checks += 1
            if used & 1 << nxt:
                pruned += 1
                continue
            next_text = text + chars[nxt]
            if prefixes is not None:
                if next_text not in prefixes:
                    pruned += 1
                    continue
                dfs(nxt, used | 1 << nxt, cells + [nxt], next_text)
            else:
                child = node.children.get(chars[nxt])
                if child is None:
                    pruned += 1
                    continue
                dfs(nxt, used | 1 << nxt, cells + [nxt], next_text, child)

    for i, char in enumerate(chars):
        if prefixes is not None:
            if char in prefixes:
                dfs(i, 1 << i, [i], char)
            else:
                pruned += 1
        elif char in trie.children:
            dfs(i, 1 << i, [i], char, trie.children[char])
        else:
            pruned += 1
    return found, states, checks, pruned


def adaptive(chars, candidates, adjacent):
    found, states, checks, pruned = {}, 0, 0, 0
    trie = make_trie(candidates)

    def dfs(i, used, cells, node):
        nonlocal states, checks, pruned
        states += 1
        if node.word:
            found[node.word] = path(cells)
            remove(node.word)
            node.word = None
        if not node.left:
            return
        for nxt in adjacent[i]:
            checks += 1
            child = node.children.get(chars[nxt])
            if used & 1 << nxt or child is None or not child.left:
                pruned += 1
                continue
            dfs(nxt, used | 1 << nxt, cells + [nxt], child)

    def remove(word):
        node = trie
        node.left -= 1
        for char in word:
            node = node.children[char]
            node.left -= 1

    for i, char in enumerate(chars):
        child = trie.children.get(char)
        if child and child.left:
            dfs(i, 1 << i, [i], child)
        else:
            pruned += 1
    return found, states, checks, pruned


def benchmark(board, dictionary, minimum):
    searches = [
        ("Brute-force DFS", brute),
        ("Prefix-set DFS", prefix),
        ("Trie DFS", lambda c, d, a: trie_search(c, d, a)),
        ("Trie DFS with subtree pruning", adaptive),
    ]
    results = []
    for name, search in searches:
        results.append(run(name, board, dictionary, minimum, search))
    return results


def app():
    st.title("Boggle Algorithm Benchmark")
    st.write("Compare four ways to find words on a 4×4 board.")

    with st.form("benchmark"):
        st.subheader("Board")
        default = "CATS\nRATE\nLION\nPEND".splitlines()
        cells = []
        for row in range(SIZE):
            columns = st.columns(SIZE)
            for column, cell in zip(columns, default[row]):
                cells.append(
                    column.text_input(
                        f"Row {row + 1}, column {len(cells) % SIZE + 1}",
                        cell,
                        max_chars=1,
                        label_visibility="collapsed",
                        key=f"cell-{row}-{len(cells) % SIZE}",
                    )
                )
        board_text = "\n".join(
            "".join(cells[row * SIZE : (row + 1) * SIZE]) for row in range(SIZE)
        )
        minimum = st.slider("Minimum word length", 3, 16, 3)
        uploaded = st.file_uploader("Dictionary (optional)", type="txt")
        run_button = st.form_submit_button("Run benchmark")

    if run_button:
        try:
            board = board_from(board_text)
            if uploaded:
                dictionary, rejected = words_from(
                    uploaded.getvalue().decode("utf-8", errors="replace").splitlines()
                )
            else:
                dictionary, rejected = words_from(
                    DEFAULT_FILE.read_text(encoding="utf-8").splitlines()
                )
            st.session_state.results = benchmark(board, dictionary, minimum)
            st.session_state.board = board
            st.session_state.dictionary_size = len(dictionary)
            st.session_state.rejected = rejected
        except (OSError, UnicodeError, ValueError) as error:
            st.error(str(error))
            return

    if "results" not in st.session_state:
        return

    results = st.session_state.results
    board = st.session_state.board

    st.success(f"Found {len(results[0].words)} words across {len(results)} algorithms.")
    st.caption(
        f"{st.session_state.dictionary_size} valid dictionary words; "
        f"{st.session_state.rejected} rejected entries."
    )
    rows = []
    for result in results:
        row = asdict(result)
        row.update(
            algorithm=row.pop("name"),
            preprocessing_ms=round(row.pop("prep") * 1000, 3),
            search_ms=round(row.pop("search") * 1000, 3),
            words_found=len(result.words),
        )
        row.pop("words")
        rows.append(row)
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.subheader("Performance charts")
    chart = pd.DataFrame(
        [
            {
                "algorithm": result.name,
                "total_ms": round((result.prep + result.search) * 1000, 3),
                "states": result.states,
                "pruned": result.pruned,
            }
            for result in results
        ]
    )
    st.bar_chart(chart, x="algorithm", y="total_ms", horizontal=True)
    st.caption("Total benchmark time in milliseconds")
    st.bar_chart(chart, x="algorithm", y="states", horizontal=True)
    st.caption("DFS states explored")
    st.bar_chart(chart, x="algorithm", y="pruned", horizontal=True)
    st.caption("Branches pruned")

    st.subheader("Explore a word path")
    selected = st.selectbox("Word", sorted(results[0].words))
    selected_path = results[0].words[selected]
    selected_cells = set(selected_path)
    for row in range(SIZE):
        columns = st.columns(SIZE)
        for column in range(SIZE):
            letter = board[row][column]
            if (row, column) in selected_cells:
                columns[column].success(letter)
            else:
                columns[column].info(letter)
    st.caption(
        f"{selected}: "
        + " → ".join(f"({row + 1}, {column + 1})" for row, column in selected_path)
    )

    with st.expander("How the algorithms work and their complexity"):
        for result in results:
            idea, complexity = ALGORITHM_INFO[result.name]
            st.markdown(f"**{result.name}**  \n{idea}  \n*Complexity:* {complexity}")
        st.markdown(
            "**How these bounds are derived:** `N` is the 16 possible starting "
            "cells, `B` is the maximum of 8 neighboring choices, and `L` is "
            "the maximum path length (16). Therefore, the loose path-search "
            "bound is `O(N x B^L)`. Prefix-set DFS adds an `O(L)` string "
            "operation per extension, while trie transitions are average "
            "`O(1)`. `S` is the total candidate-dictionary character count, "
            "and `W x L` is the cost of removing each discovered word from "
            "the subtree-pruned trie."
        )

    with st.expander("All discovered words and paths"):
        for word, cells in sorted(results[0].words.items()):
            coordinates = ", ".join(f"({r + 1}, {c + 1})" for r, c in cells)
            st.write(f"{word}: {coordinates}")


if __name__ == "__main__":
    app()
