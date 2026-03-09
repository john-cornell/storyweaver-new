# REQUIRED_FIXES_FROM_PR_COMMENTS — Interactive Story Mode

## Status: ALL ADDRESSED

## Brutal PR Review Findings

### 1. **BLOCKER: Run button overwrites interactive content** ✅ FIXED
**File:** `app.py`  
**Issue:** When in interactive mode, clicking "Run" calls `do_auto_expand_next` with `steps=[]`, `history=[]`, which overwrites the Working panel with empty content.  
**Fix:** Run button must check `generation_mode_state` and either (a) skip/no-op when interactive, or (b) be disabled when interactive. Prefer (a) with a conditional wrapper like `_conditional_auto_expand`.

### 2. **MAJOR: Path tree "Continue from here" not implemented** ✅ FIXED
**File:** `working/interactive/ui.py`, `app.py`  
**Issue:** Plan specifies: "Click unexplored node: 'Continue from here' — set current_node_id, show prose so far, generate choices/continuation." The path tree HTML shows "Continue" text but there is no click handler. Users cannot jump to unexplored branches.  
**Fix:** Add clickable "Continue" links/buttons in the path tree that trigger a handler to set `current_node_id` to the unexplored node and generate continuation. This requires either (a) JavaScript in the HTML to call a Gradio event, or (b) a different UI approach (e.g. dropdown of unexplored nodes with "Continue" button). Gradio HTML does not support dynamic click handlers easily—consider a separate "Jump to branch" dropdown listing unexplored nodes.

### 3. **MAJOR: Nav does not handle interactive mode** ✅ FIXED
**File:** `ui/nav.py`  
**Issue:** Plan says "Include interactive-specific outputs when mode=interactive." Nav uses `build_current_story_html(steps)` and `build_history_markdown(history)`. For interactive mode, `steps` and `history` are empty, so navigating to Working shows empty content. `working_path_tree_html` is not in nav_outputs.  
**Fix:** Add `interactive_state` and `generation_mode_state` to nav_inputs. When mode=interactive and interactive_state has nodes, use `get_prose_to_node` + choices for current story and `build_path_tree_html` for path tree. Add `working_path_tree_html` to nav_outputs. Update `_nav_outputs` signature and all nav functions.

### 4. **MINOR: No-op return tuple inconsistency in _do_interactive_choice/_do_interactive_custom** ✅ FIXED
**File:** `app.py` lines 164, 194  
**Issue:** No-op returns `("", "", "", "")` for the four placeholder outputs. The success path returns `gr.update()` for choice_a_btn and choice_b_btn. For consistency and to avoid potential Gradio issues, no-op should return `gr.update()` for buttons.  
**Fix:** Change no-op return from `"", "", "", ""` to `gr.update(), gr.update(), "", ""` for the button and path_tree outputs.

### 5. **MINOR: Lazy import in _conditional_auto_expand** ✅ FIXED
**File:** `app.py` lines 244–252  
**Issue:** Imports from `working` are done inside the function. Project style uses top-level imports.  
**Fix:** Move `build_current_story_html`, `build_erl_tab_content`, etc. to top-level imports (already imported). Remove the redundant inner import block and use the existing top-level imports.

### 6. **NITPICK: interactive_choice_row and interactive_custom_row unused** ✅ FIXED
**File:** `app.py` lines 339, 343  
**Issue:** `interactive_choice_row` and `interactive_custom_row` are assigned but never used. Plan suggests Choice A/B could be hidden in expansion mode.  
**Fix:** Either (a) remove the `as` clause if not needed, or (b) use them to set `visible=False` when mode=expansion and `visible=True` when mode=interactive. Given complexity, (a) is acceptable for now—remove the variable names if they serve no purpose.

### 7. **NITPICK: Type hints for log_entries** (deferred; low impact)
**File:** `app.py`  
**Issue:** `log_entries: list` should be `list[str]` for clarity.  
**Fix:** Add proper type hints where missing.
