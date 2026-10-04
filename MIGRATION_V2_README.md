# SvenskaKort 2.0 migration build

This build migrates the app from the old Rivstart-derived datasets to the Kelly-based CEFR dataset.

## Included
- 8425 Kelly cards: A1, A2, B1, B2, C1, C2
- English translations and NST-derived IPA where available
- 4367 safe old-ID -> Kelly-ID progress mappings
- one-time, idempotent progress migration
- old progress/status keys are preserved
- old cards with no safe Kelly equivalent are ignored, not deleted

## Important deployment test
Test on the SAME origin used by current users (svenskakort.com).
Do not clear browser/site storage before the upgrade test.

1. Open current production version and learn/mark several cards.
2. Note New/Learning/Due/Learned counts.
3. Deploy/test this v2 build on the same origin.
4. Confirm mapped cards retained progress.
5. Reload several times; counts must not reset or double-migrate.
6. Confirm A1–A2, B1–B2 and C1–C2 material groups work.
7. Confirm Daily Review and Reset Progress still work.

Migration completion key:
progress_migration_rivstart_to_kelly_v1_done
