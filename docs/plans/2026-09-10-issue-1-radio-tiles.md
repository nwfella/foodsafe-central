# Issue #1 — "Change Check Boxes to Radio Buttons" — feasibility + plan (DRAFT, not implemented)

Repo: `nwfella/foodsafe-central` · Issue: #1 · Opened: 2026-09-10 04:52 UTC by **LilaMandalay18** (`authorAssociation: NONE` — not a collaborator)
Status: OPEN, no labels. Issue body is only *"Thank you."* — the substance is in the 6-comment thread.

> **UPDATE — implemented (Option 1).** All 8 plan steps done: five radio views (4 scopes + "All recalls"),
> radio-dot affordance, EN/FR tooltips, arrow-key navigation, "custom" badge, baked no-JS snapshot intact.
> Verifier rewritten for radio semantics and green at **107 checks**, including the ticket's core promise —
> every card's number equals its result set (fda 1377/1377, usda 45/45, week 2/2, all 1422/1422, active 555/555).
> The old multi-select checks are gone. The step-8 reply was posted to issue #1.

## 1. What is actually being asked

The thread, in order:

| Who | Comment | Reading |
|---|---|---|
| LilaMandalay18 | *(issue title)* "Change Check Boxes to Radio Buttons" + body "Thank you." | Wants the four top cards to be radio buttons |
| nwfella | "Change which check boxes into Radio Buttons. We have many check boxes, your going to need to be far more specific!" | Asked for clarification |
| LilaMandalay18 | "Veuillez pardonner le mauvais anglais de cette pauvre Française. Je veux parler des **quatre cartes**, Monsieur. Lila 💋" | "the four cards" — i.e. the four stat tiles at the top |
| nwfella | "I suggest the following: rosetta stone (English)" | *(off-topic joke; she read it literally)* |
| LilaMandalay18 | "Mercí, but I do not dabble with these demonic religions. 👼" | Thread derailed by the language gap |
| nwfella | Restates: change the four cards — Active Recalls (FDA + USDA), Published in the last 7 days, FDA Food Recalls 12 months, USDA FSIS 12 month recalls — *"from multi selectable checkboxes to radio buttons... This will only allow one of those 4 cards to be selected at one time."* | Explicit, unambiguous scope |
| LilaMandalay18 | **"Oui! C'est bon!!! 💫"** | **Confirms the restatement.** This is the ticket. |

**Ticket (confirmed):** the four stat tiles become a **single-select (radio) group** — choosing one clears the others.

Note: the tester's handle `LilaMandalay18` is almost certainly the **Lil Mandalay** already credited in the footer. The attribution is right; this is the friend using the app.

## 2. Verdict

**Feasible — small change, low risk, no data or infrastructure work.** It touches UI semantics only:

| Area | Change |
|---|---|
| `template.html` | tile markup/ARIA, tile CSS affordance, tile click semantics, `syncUI()` |
| `scripts/verify_site.js` | ~20 of 96 checks currently encode *multi-select* tile semantics — they must be rewritten |
| `README.md` | document the radio "views" |
| `build_data.py` / `bake.py` / data | **no change** |

Effort: roughly one session. The real cost is the verifier rewrite, not the feature.

**But it reverses part of what shipped yesterday** (multi-select clickable tiles), so it needs a semantic decision — see §5.

## 3. The tester is right about something real

Measured against current data (1,422 records):

| Tile label | Number on the card | What you actually get by clicking it today |
|---|---|---|
| Active recalls (FDA + USDA) | 555 | 555 ✅ |
| Published in the last 7 days | 2 | 2 ✅ |
| FDA food recalls · 12 months | **1,377** | **510** ❌ (status=ACTIVE is still applied) |
| USDA FSIS recalls · 12 months | 45 | 45 ✅ *(coincidence — every FSIS notice is treated as active)* |

So the FDA card promises 1,377 recalls and delivers 510 — a 63 % shortfall. Turning each card into a self-contained scope (which is what radio semantics implies) **fixes that mismatch** by making each card's number equal the result you get. That is a correctness win, not just a preference.

## 4. What radio semantics costs — less than it looks

Choosing one card clears the other three, so these combinations can no longer be assembled *from the tiles*:

| Combination | Count | Still reachable after the change? |
|---|---|---|
| active + last 7 days | 2 | ✅ via the status select + the 7-day chip |
| FDA + active only | 510 | ✅ via the agency select + status select |
| USDA + active only | 45 | ✅ trivially (all FSIS notices are active) |

Because the **selects and quick chips stay**, no capability is actually lost — only the tiles stop combining. The one genuinely new constraint: **a radio group cannot be un-clicked**, so there must be an explicit way back to "everything", or users get stuck in a scope.

## 5. Options

### Option 1 — Literal radio group, as "views" (RECOMMENDED)
Each card becomes a complete, self-contained preset whose number equals its result:

| Card | Sets |
|---|---|
| Active recalls | status = active |
| Published in the last 7 days | date window = 7 days (all statuses, so the count 2 is honest) |
| FDA food recalls · 12 months | agency = FDA, all statuses (1,377) |
| USDA FSIS recalls · 12 months | agency = USDA FSIS, all statuses (45) |

Plus a 5th neutral option **"All recalls · 12 months" (1,422)** so the group is never a trap. Uses the tiles' own visual; selects/chips remain refinements, and using one marks the group as **"custom"** (no card checked) rather than lying about which card is active.

- ✅ Exactly what she confirmed · fixes the 1,377→510 mismatch · nothing lost (selects remain)
- ⚠️ The FDA/USDA views then include *terminated* recalls. Mitigation: the card already shows ACTIVE/TERMINATED, the count line says "all statuses", and the default landing view stays "Active recalls".

### Option 2 — Radio group without changing scope semantics
The four cards become mutually exclusive but each keeps today's refinements (so the FDA card still shows 510). She gets radios; the number/result mismatch remains unless we also relabel the card.

- ✅ Smallest change · least test churn
- ⚠️ Doesn't fix the underlying inconsistency · the 1,377 label stays wrong

### Option 3 — Radios for the agency pair only
FDA/USDA become exclusive; Active / last-7-days stay independent modifiers.

- ✅ Keeps the most useful combination (active + new)
- ⚠️ Two of the four cards would *not* behave as radios → likely to re-confuse the tester; contradicts her confirmed wording

## 6. Recommended plan of action (Option 1)

1. **Semantics** — add a single `view` field to the existing filter state (`state.f.view`) holding one of `active | week | fda | usda | all`. Selecting a view sets its dimensions and clears the others from the view-owned dimensions; the selects/chips write their own dimensions and clear `view` (→ "custom").
2. **Markup + ARIA** — wrap the tiles in `role="radiogroup"` labelled *"Filter — choose one"*; each tile becomes `role="radio"` + `aria-checked`; roving `tabindex` with ←/→ arrow-key navigation; keep them as `<button type="button">` styled as cards.
3. **Visual affordance** — replace the pressed `✓` with a **radio dot** (filled = selected) and dim unselected cards, so the cards stop *looking* like checkboxes (the root cause of the confusion). Add a 5th "All recalls" option.
4. **Language** — EN + FR `title`/`aria-label` tooltips on the group and each card (she is a French speaker; the thread derailed on wording, so plain-language help is the actual fix). Short inline line: *"Choose one — or use the filters below to refine"* / *"Choisissez une option"*.
5. **Keep every existing behaviour** — chart-follows-filter, month-bar click, tiles↔selects↔chips sync (now including "custom" state), ↺ Reset returns to the default view, no-JS snapshot.
6. **Rewrite the verifier** — replace the ~20 multi-select tile checks with: exactly one card checked at a time; clicking a card clears the others; numbers equal results (1377 → 1,377 rows); arrow-key navigation; "All" clears the scope; a select/chip marks the group custom; month-click still composes; ↺ Reset restores the default card. Target: all checks green before push.
7. **Docs** — README section on the radio "views"; note the FSIS "class n/a" and terminated-included caveats.
8. **Deploy** — bake, verify, push, poll the live URL to a byte-match (the established pipeline).

## 7. Risks / edge cases

- **Terminated recalls inside the FDA/USDA views** (see §5 mitigation).
- **Month-bar click + view** — month stays a *refinement*; it should not clear the radio group, just appear in the chart/list header.
- **"Last 30 days" chip** — if the tile owns "7 days", the 30-day chip stays as the refinement path; if that reads oddly, promote it to a 6th view.
- **Keyboard/touch** — radios need arrow-key support and ≥44 px tap targets; the group must announce "1 of 5".
- **Regression surface** — `syncUI()` currently assumes independent booleans; it becomes a state machine. The verifier is the safety net.

## 8. Suggested reply to the tester (not posted, EN + FR)

> **EN** — Thank you Lila, and sorry for the confusion earlier — that one was on me. Confirmed: the four cards at the top will become radio buttons, so only one can be chosen at a time, each showing exactly the recalls its number promises, plus an "All recalls" option so you can always get back to everything. The filters underneath stay available for narrowing further. Merci! 🤗
>
> **FR** — Merci Lila, et pardon pour la confusion — c'était de ma faute. Confirmé : les quatre cartes du haut deviennent des boutons radio, une seule sélection à la fois, chacune affichant exactement les rappels annoncés, avec en plus une option « Tous les rappels » pour revenir à la liste complète. Les filtres en dessous restent disponibles pour affiner. Merci ! 🤗
