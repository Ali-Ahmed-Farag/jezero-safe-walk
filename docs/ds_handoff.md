# DS Handoff & File Contracts

## 1. أمثلة مقاييس المسار (Path Metrics Examples)

*(B3): الأرقام القديمة هنا (0.62/2.92/4.38 كم لسيناريو 1/3/5) كانت محسوبة على `analysis/presets_fixed.json` — fixture قديم pre-canonical بإحداثيات NE مختلفة وإسقاط متقاعد (bounds ثابتة + `(W-1)/(H-1)`). الملف ده اتقاعد من الـ workflow: السكريبتات دلوقتي بتقرأ مباشرة من المصادر الـ canonical: `web/data/presets.json` (DE2) و `web/data/grid_meta.json` (DE1). النتائج الجديدة بعد إعادة التشغيل على الـ endpoints الـ canonical بالبروفايل Standard (safe: 10, hard: 16, forbidden: 16) — الطول وأقصى ميل حتميان (deterministic)، وزمن التشغيل wall-clock تقريبي:*

- **scenario_1 (Short):** الطول 0.44 كم، أقصى ميل 1.75°، موجودة ✓ (مسافة المركبة الفعلية: 1.002 كم — المسافة الـ A* أقصر لأنها أقصر مسار ممكن على الشبكة، مش مسافة المركبة).
- **scenario_3 (Medium):** الطول 1.01 كم، أقصى ميل 6.50°، موجودة ✓ (مسافة المركبة الفعلية: 3.001 كم).
- **scenario_5 (Advanced):** الطول 0.14 كم، أقصى ميل 3.25°، موجودة ✓ (مسافة المركبة الفعلية: 5.001 كم).
- **scenario_8 (Long):** الطول 1.42 كم، أقصى ميل 5.25°، موجودة ✓ (مسافة المركبة الفعلية: 8.003 كم). *(ملاحظة: في الـ fixture القديم كان scenario_8/Conservative بيطلع no_path — الـ endpoints الـ canonical مختلفة فبقت موجودة.)*

الـ 24 combination كاملة (4 سيناريوهات × 3 بروفايلات × 2 وضعية) كلها موجودة في `analysis/scenario_matrix.csv` (B3).

## 2. أوامر إعادة التوليد (Regeneration Commands)
*(ملاحظة: سكريبتات التحقق والإسقاط تعتمد على ملف DE2 النهائي `data/processed/rover_track_clean.csv` وملف `science_targets.geojson`)*

ملاحظة (B6): ملف `web/data/elev_dm_i16.bin` بيتولّد من مولّد DE1 الرسمي الوحيد `pipeline/export_elev_bin.py` (ضرب Float64 + تقريب نصف-حتى + معالجة NoData + فحص ±Inf) وسكريبتات DS ما بتولّده — DS بيستهلك نسخة DE1 الموثقة والمتحقق منها. وكمان حساب الميل (`analysis/compute_slope.py`) بينفذ فحصًا صريحًا: أي بكسل NoData/NaN/±Inf بيوقف التشغيل فورًا قبل حساب الميل — ممنوع الاستيفاء أو الاستبدال.

عشان تعيد توليد الملفات من الصفر بالترتيب:
1. حساب الميل: `python analysis/compute_slope.py` → يطلع `web/data/slope_u8.bin`
2. إسقاط الأهداف ونقاط المركبة: `python analysis/project_targets.py` → يحدّث `analysis/projected_points.json`
3. التحقق العلمي: `python analysis/validate_rover.py` → يطلع `web/data/validation_results.json`
4. اختبار المسارات: `node analysis/test_astar.js` (بيختبر A* على 6 حالات)
5. توليد مصفوفة السيناريوهات: `python analysis/run_matrix_and_fix.py` → بيطلع `analysis/scenario_matrix.csv` — (B3): بيقرأ مباشرة من `web/data/presets.json` (DE2) و `web/data/grid_meta.json` (DE1)، ومش بيكتب ولا بيستهلك `analysis/presets_fixed.json` (اتقاعد كـ fixture — الملف الموجود اتساب للتاريخ فقط، مفيش أي سكريبت بيستخدمه).

## 3. توثيق صيغة `cost_default.json`
```json
{
  "Conservative": { "safe": 6, "hard": 10, "forbidden": 10 },
  "Standard": { "safe": 10, "hard": 16, "forbidden": 16 },
  "Extended": { "safe": 14, "hard": 20, "forbidden": 20 }
}

## 4. B15 - Rover projection evidence (restored 2026-11-14)

`analysis/projected_points.json` was regenerated with the full 32,003-point rover track
(the previous regeneration at ef753b8 ran without the track CSV present and embedded 0 track points).

- **Command (reproducible):** `python analysis/project_targets.py` (run from the repo root; requires the
  track-owner inputs below to be present as untracked working files - they are NOT committed on DS).
- **Inputs (owner, sha256):**
  - `data/processed/rover_track_clean.csv` (DE2-owned, untracked on DS): `71c1b04e9f461107167fe2b414a7aa05f334a15a9d2c299d6f276f26fe35dbdd`
  - `data/processed/dem_20m_crop.tif` (DE1 deliverable, git blob `b746795363c0baad02696e9c3711591c523ec88c873ae28a0f8faded122041ae` content)
  - `web/data/science_targets.geojson` (DE2 canonical, git blob `f6b0c40486b0`)
  - `web/data/grid_meta.json` (DE1 canonical, git blob `2d908027b01b41955ee92f978de6c5bc7bfe073f`)
- **Output:** `analysis/projected_points.json`, sha256 `0bd4311b61b406c081385183aac3bd1081d501c9b90df6c6e3541ecbf020ded1` (10,028,057 bytes)
- **Results:** `rover_track_count = 32003`, `rover_track_in_bounds = 32003/32003` (all points inside the DE1
  outer-corner grid bounds); 3 science targets all `in_bounds = true`; landing point = (row 666, col 641) which
  matches the canonical floor-based grid contract exactly.
- **Spot-check:** 5 sample points (sols 0, 130, 340, 380, 1815) re-derived independently from lon/lat via the
  `grid_meta.notes` floor formula - all match the file's row/col exactly.
