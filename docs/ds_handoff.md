# Data Science — Handoff & Integration Checklist (Jezero Safe Walk)

تم الانتهاء من كافة مخرجات مسار **Data Science** ورفعها على فرع `analysis` في المستودع. هذا الملف يوضح المخرجات الجاهزة للاستخدام وما هو مطلوب من كل مسار لإتمام الاختبار النهائي والتسليم.

---

## 1. ملخص ما تم تسليمه من مسار Data Science (على فرع `analysis`)

### أ. ملفات التطبيق (`web/data/`)
- **`slope_u8.bin` & `slope_meta.json`**: مصفوفة الميل لكامل شبكة Jezero (`1016 × 1075` بكسل، دقة `20 m/pixel`) بصيغة `Uint8` (`slope_scale = 4`، دقة `0.25°`، وحد `NoData/Border = 255`).
- **`astar.js`**: محرك تخطيط المسارات (`findRoute`) يعمل لحظياً داخل المتصفح (`5.3 – 17.7 ms`) بوضعَي `safest` و `shortest`.
- **`cost_default.json`**: تعريفات ملفات البدلة الثلاثة (`Conservative: 6°/10°`، `Standard: 10°/16°`، `Extended: 14°/20°`)، ألوان الفئات للواجهة، ومعادلة مؤشر المخاطرة (`Low / Moderate / High`).
- **`route_bank.json`**: بنك مسارات جاهزة (خطة بديلة فورية).
- **`validation_results.json`**: نتائج التحقق العلمي على **32,003 نقطة** من مسار Perseverance (`Pitch r = 0.89`, `Roll r = 0.86`)، جدول فئات الميل، اختبار **Rover Replay** لمقطع `4 km`، وعينة `2,500` نقطة للرسم البياني في الموقع.

### ب. الرسومات والتوثيق (`analysis/charts/` & `docs/`)
- **`analysis/charts/slope_map.png`** و **`analysis/charts/validation_charts.png`**: رسومات علمية عالية الدقة (`300 DPI`) جاهزة للاستخدام في الشرائح والـ Proposal.
- **`docs/assumptions.md`** و **`docs/sources.md`** و **`ds_technical_report.md`**: التوثيق العلمي الكامل، الافتراضات والحدود، وإفصاح الأدوات.

---

## 2. المطلوب من كل مسار لإغلاق مرحلة التكامل (Integration)

### أولاً: المطلوب من Data Engineer 1 (`DE1`)
1. **تأكيد تطابق `web/data/grid_meta.json`**:
   - التأكد من أن `width = 1016` و `height = 1075` وحجم البكسل `20.0 m` والحدود الجغرافية (`bounds`) في `grid_meta.json` مطابقة تماماً لملف `data/processed/dem_20m_crop.tif` لضمان عدم وجود أي إزاحة مكانية بين طبقة الميل وطبقات الخريطة (`ctx_basemap.jpg` و `hillshade.png`).
2. **دمج النتائج في الـ Proposal**:
   - إدراج ملخص المنهجية (Horn 3×3 + A*) ونتائج التحقق (`r = 0.89` للـ Pitch، `r = 0.86` للـ Roll، واختبار Rover Replay) مع التنويه بأن المخرجات تقديرية للتخطيط المبدئي وليست للملاحة اللحظية.
   - يمكن استخدام الصور المرفقة في `analysis/charts/`.

---

### ثانياً: المطلوب من Data Engineer 2 (`DE2`)
1. **تسليم ملف `web/data/presets.json`**:
   - رفع ملف السيناريوهات الأربعة المعتمدة (`presets.json`) على المستودع حتى نتمكن من تشغيل اختبار التحقق الآلي لخوارزمية `astar.js` على جميع السيناريوهات والتأكد من نجاحها.
2. **دمج النتائج والرسومات في العرض التقديمي (Slides)**:
   - استخدام الرسومات الجاهزة في `analysis/charts/validation_charts.png` و `analysis/charts/slope_map.png` في شريحة التحقق العلمي (`Validation`).
   - إبراز الأرقام الرئيسية: **32,003 نقطة تحقق**، **ارتباط `0.89` (Pitch) و `0.86` (Roll)**، وزمن استجابة **أقل من `18 ms`** في المتصفح.

---

### ثالثاً: المطلوب من `Full Stack` (و `UI/UX`)
1. **دمج فرع `analysis` في الفرع الرئيسي**:
   - عمل Merge لملفات `web/data/` (`slope_u8.bin`, `astar.js`, `validation_results.json`, `cost_default.json`, `slope_meta.json`).
2. **ربط `astar.js` بالواجهة التفاعلية**:
   - استدعاء `findRoute({ slope, width, height, pixelM: 20, start, end, profile, mode, slopeScale: 4 })` عند اختيار نقطتي البداية والنهاية أو عند تغيير نوع البدلة / الـ Slider.
   - التعامل مع حالة `found: false` بإظهار تنبيه واضح للمستخدم (مثلاً: *"لا يوجد مسار آمن ضمن حدود البدلة الحالية — جرّب ملف بدلة أعلى"*).
3. **عرض مؤشرات المسار ولوحة التحقق (Validation Panel)**:
   - استخدام تعريفات الألوان وقواعد مؤشر المخاطرة (`Low / Moderate / High`) الموثقة في `web/data/cost_default.json`.
   - قراءة `web/data/validation_results.json` لعرض مقاييس الدقة والرسم البياني لعينة الـ `2,500` نقطة.
   - إظهار تنويه واضح في الواجهة بأن جميع المسارات والأزمنة تقديرية للتخطيط المبدئي.
4. **تأكيد إجراء اختبار التكامل (`Integration Test`)**:
   - إبلاغنا فور الدمج لتجربة الخريطة والمسارات معاً والتأكد من تطابق الإحداثيات وعدم وجود أي أخطاء في المتصفح.