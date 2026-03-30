# HiBy Sorting Patch: Technical Documentation

## The Original Issue
The HiBy player sorts music using an internal function that converts characters into Pinyin (to support Chinese) and then compares them alphabetically. This system presented several limitations:

* **Articles:** It does not ignore articles such as "The", "Der", "Die", etc.
* **Symbols:** It does not ignore leading symbols like `(`, `.`, `"`, or `'`
* **Numerical Sorting:** It places the `#` category (symbols and numbers) at the bottom of the list instead of the top.
* **Scrollbar:** The side scrollbar ranges from A to Z, with # positioned at the end.

---

## The Solution
The patch utilizes a "code cave" (a section of empty space) starting at address `0x41b8b0`. This area contains approximately 18,000 bytes of zeros in the original file, which were used to write new functions in **MIPS machine language**.

### 1. "strip_articles" Function (at 0x41b8b0)
When the player compares two names to determine their order, it first passes through this function to check for leading articles.
* **Format:** Database names are in **UTF-16** (2 bytes per character).
* **Logic:** The function checks if the string begins with specific articles followed by a space: *The, Der, Die, Das, Il, Lo, La, Le, Les, El*.
* **Sensitivity:** The check is case-insensitive.
* **Result:** If an article is found, the pointer is moved forward. For example, "The Slow Rush" is treated as "Slow Rush" and sorted under **S**.

### 2. "paren_strip" Function (at 0x41bce0)
This is called **before** `strip_articles`.
* **Logic:** It checks if a name starts with `(`, `.`, `"`, or `'` and skips them.
* **Sequence:** It can skip multiple consecutive symbols.
* **Result:** `"Hello"` becomes `Hello` and is sorted under **H**.

### 3. "collation_wrapper" Function (at 0x41bafc)
This is the central logic hub for name comparison.
1. It calls `paren_strip` on both names (which subsequently calls `strip_articles`).
2. It classifies the first character of each "cleaned" name into categories:
    * **Category 0 (Symbols):** Anything that is not a letter or a digit, including Unicode characters like `†` (range 0x2000-0x2FFF).
    * **Category 1 (Digits):** Numbers 0-9.
    * **Category 2 (Letters):** A-Z, a-z, and accented letters (≥ 0xC0).
3. If categories differ, it returns the difference immediately (Symbols > Numbers > Letters).
4. If categories are the same, it calls the player's original Pinyin-based comparison function.

### 4. System Integration
The original comparison function was called from 8 different points in the code (within functions that populate database tables: *all, ab, full, media2*).
* **Redirection:** Each of these 8 points was modified to call the `collation_wrapper` instead.
 * **Trampoline:** A "trampoline" at `0x493480` redirects to the wrapper.

### 5. Scrollbar: # at the Top
The logic for the side scrollbar was originally: *Position + 'A' (65) → if > 'Z' → show '#'*.
* **Modification:** It was changed to: *Position + 64 → if < 'A' → show '#'*.
* **Result:** Position 0 becomes '#', followed by 1='A', 2='B', etc.

### 6. Navigation Logic
Originally, touching '#' calculated a position at the end of the list.
* **Modification:** The calculation was changed to "position = 0".
* **Result:** Tapping '#' now jumps to the beginning of the list where symbols and numbers are located.

---

## Summary of Changes
The binary file size remains unchanged, as all modifications overwrite existing bytes (zeros in the code cave or original instructions elsewhere).

| Component | Address | Size |
| :--- | :--- | :--- |
| `strip_articles` | `0x41b8b0` | ~508 bytes|
| `paren_strip` | `0x41bce0` | ~88 bytes |
| `collation_wrapper` | `0x41bafc` | ~324 bytes |
| 8 DB Function Redirects | Various | 4 bytes each |
| Trampoline | `0x493480` | 8 bytes |
| Scrollbar # at Top | `0x4d8c6c`, `0x4d8ce8`, `0x4d8cec`, `0x4d8cf8` | 4 bytes each  |
| # Navigation → Start | `0x4d883c`, `0x4d8840` | 4 bytes each  |
