# DS Handoff & File Contracts

## 1. أمثلة مقاييس المسار (Path Metrics Examples)
تم اختبار دالة `pathMetrics` في `web/data/metrics.js` على 3 مسارات حقيقية (سيناريو 1، 3، 5) باستخدام بروفايل Standard (safe: 10, hard: 16, forbidden: 16).
- **scenario_1 (Short):** الطول 0.62 كم، متوسط ميل 2.28°، أقصى ميل 4°، 100% آمن، صعود 7.9م، هبوط 5.7م، الوقت 0.31 ساعة، مستوى المخاطر: منخفض.
- **scenario_3 (Medium):** الطول 2.92 كم، متوسط ميل 3.07°، أقصى ميل 14.75°، 94.19% آمن (5.81% صعب)، صعود 109.8م، هبوط 19.3م، الوقت 1.46 ساعة، مستوى المخاطر: متوسط.
- **scenario_5 (Advanced):** الطول 4.38 كم، متوسط ميل 2.5°، أقصى ميل 12.75°، 96.77% آمن (3.23% صعب)، صعود 136.5م، هبوط 9.4م، الوقت 2.19 ساعة، مستوى المخاطر: منخفض.

## 2. أوامر إعادة التوليد (Regeneration Commands)
*(ملاحظة: سكريبتات التحقق والإسقاط تعتمد على ملف DE2 النهائي `data/processed/rover_track_clean.csv` وملف `science_targets.geojson`)*

عشان تعيد توليد الملفات من الصفر بالترتيب:
1. حساب الميل: `python analysis/compute_slope.py` → يطلع `web/data/slope_u8.bin`
2. إسقاط الأهداف ونقاط المركبة: `python analysis/project_targets.py` → يحدّث `analysis/projected_points.json`
3. التحقق العلمي: `python analysis/validate_rover.py` → يطلع `web/data/validation_results.json`
4. اختبار المسارات: `node analysis/test_astar.js` (بيختبر A* على 6 حالات)
5. توليد مصفوفة السيناريوهات: `python analysis/run_matrix_and_fix.py` → بيطلع `analysis/scenario_matrix.csv` و `analysis/presets_fixed.json`

## 3. توثيق صيغة `cost_default.json`
```json
{
  "Conservative": { "safe": 6, "hard": 10, "forbidden": 10 },
  "Standard": { "safe": 10, "hard": 16, "forbidden": 16 },
  "Extended": { "safe": 14, "hard": 20, "forbidden": 20 }
}