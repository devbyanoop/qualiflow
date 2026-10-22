import { useTranslations } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { LocaleSwitcher } from "@/components/locale-switcher";

export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <HomePageContent />;
}

function HomePageContent() {
  const t = useTranslations("HomePage");

  return (
    <main className="relative flex flex-1 flex-col items-center justify-center gap-6 px-6 py-16 text-center">
      {/* `end-6`, not `right-6` -- a logical-property utility so this
          sits on the trailing edge in both LTR and RTL, not always the
          visual right. */}
      <div className="absolute top-6 end-6">
        <LocaleSwitcher />
      </div>
      <h1 className="text-4xl font-semibold">{t("title")}</h1>
      <p className="text-lg text-gray-600 dark:text-gray-300">{t("tagline")}</p>
      <p className="rounded-full border border-gray-300 px-4 py-1 text-sm text-gray-500">
        {t("status")}
      </p>
      <p className="max-w-prose text-sm text-gray-500">{t("description")}</p>
    </main>
  );
}
