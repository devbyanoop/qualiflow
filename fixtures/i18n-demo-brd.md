# BRD excerpt — Minimum Age for Account Opening (bilingual demo)

**Purpose:** Phase 0 deliverable (plan §26, build plan's "bilingual demo BRD") — proves ingestion and generation handle non-Latin, RTL script without breaking, ahead of any real localization work in the UI or case schema. Deliberately app-agnostic, unlike `novapay/brd-transfer-rule.md` — this isn't a rule about any specific target app.

**Translation note:** written with AI assistance, not reviewed by a native Arabic speaker. Good enough to prove the pipeline handles Arabic/RTL text correctly; not good enough to treat as a real jurisdiction's actual requirement without the native-speaker review the plan itself calls for (§4.5 risk mitigation) before this is used with a real design partner.

## English

> A customer must be at least 18 years old to open an account. The application's date of birth field is used to calculate age at the time of the request, not at submission review. An account-opening request from an applicant under 18 is rejected, and the applicant is shown a clear message explaining the minimum-age requirement rather than a generic error.

## العربية (Arabic)

> يجب أن يبلغ عمر العميل 18 عامًا على الأقل لفتح حساب. يُستخدم حقل تاريخ الميلاد في الطلب لحساب العمر وقت تقديم الطلب، وليس وقت مراجعته. يُرفض طلب فتح الحساب من مقدم طلب يقل عمره عن 18 عامًا، ويُعرض له رسالة واضحة تشرح شرط الحد الأدنى للعمر بدلاً من رسالة خطأ عامة.
