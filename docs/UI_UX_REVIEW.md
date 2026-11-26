# UI/UX verification checklist

This checklist applies the supplied UI/UX handbook's release checklist to the
settings dialog, in-game overlay, and animation chooser. It records code-backed
behavior separately from checks that still require a real desktop and must be
completed for a release candidate. It is not a claim of WCAG conformance or a
substitute for a visual review.

## Current implementation evidence

| Handbook criterion | Implementation / regression evidence | Release verification |
|---|---|---|
| Main task and secondary actions are visually distinct | Settings has a primary Save action and separate Cancel/Reset actions; the footer remains available while pages scroll (`source/app/settings_ui.py`). | Confirm the hierarchy is clear at 100% and 150% display scaling. |
| Long content remains usable | Settings pages scroll and the window is sized against the available screen; animation choices wrap text and use a scroll area (`source/app/settings_ui.py`, `source/app/animations/chooser.py`). | Resize the window and check long Russian and English labels. |
| Keyboard access and visible focus | Settings styles focus states; `ToggleSwitch` is Tab-focusable and supports standard button keyboard interaction. Animation chooser cards expose accessible names and keyboard selection. | Complete the keyboard-only check below on Windows. |
| Accessible names | The DLX switch and animation chooser cards set accessible names; icon-only and custom controls should be checked when changed. | Spot-check names with the platform accessibility inspector or a screen reader. |
| Animation timing | The settings toggle uses a 160 ms transition, within the handbook's 150–300 ms interaction range. | Check the transition feels responsive and does not delay the action. |
| Errors explain recovery | Settings and DLX surface human-readable states; the troubleshooting guide maps common failures to next steps (`ERRORS_AND_FIXES.md`). | Trigger an offline translation and an unavailable DLX endpoint; confirm the message suggests a next action. |
| Color contrast | Dark-theme colors and semantic states are defined in the UI stylesheets. Automated contrast ratios are not currently measured. | Measure normal text at 4.5:1 and large text at 3:1; do not rely on color alone to communicate status. |
| Reduced-motion preference | The custom switch animation is brief; a system-wide reduced-motion preference is not currently wired to the Qt UI. | Keep this as an open accessibility improvement; do not claim reduced-motion support. |

## Automated UI regression checks

On a machine with the Qt runtime, run:

```sh
QT_QPA_PLATFORM=offscreen python -m pytest source/tests/test_settings_ui.py source/tests/animations/test_chooser_ui.py -v
```

The tests verify keyboard toggling, the switch's accessible name and focus
policy, programmatic state changes without user-action signals, animation
duration, and animation chooser layout/keyboard selection. CI requires these Qt
tests on Windows via `RPCHAT_REQUIRE_QT_TESTS=1`. Linux may skip them when the
Qt platform libraries are missing; see [`TESTING.md`](TESTING.md).

## Release-candidate manual pass

- [ ] Settings at 100% and 150% display scaling; resize to a narrow window and
      verify no important control is clipped or unreachable.
- [ ] Navigate every settings page with Tab, Shift+Tab, arrows where applicable,
      Enter, Space, and Escape; confirm focus remains visible and logical.
- [ ] Check Russian and English at large text scale, including long labels,
      validation messages, status labels, and animation descriptions.
- [ ] Check contrast ratios for normal and large text; verify status is conveyed
      by text/icon as well as color.
- [ ] Exercise offline translation, invalid service address, rejected token,
      and failed game send; each error should state what happened and what to do.
- [ ] Open the animation chooser with long descriptions; verify scrolling,
      accessible names, Enter selection, and Escape cancellation.
- [ ] Record the OS, display scaling, screen-reader/keyboard checks, defects, and
      follow-up actions in the release or pull-request notes.

A failed or unperformed manual item remains open; do not mark this checklist
complete based only on lint or automated tests.
