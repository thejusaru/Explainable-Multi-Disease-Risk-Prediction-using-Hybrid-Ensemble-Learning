import type { Metadata } from "next";
import "./globals.css";
import AppHeader from "../components/AppHeader";
import { SettingsProvider } from "../lib/settings";
import { AnalysisProvider } from "../lib/analysis-store";

export const metadata: Metadata = {
  title: "Vitalis — Health Risk Projection",
  description:
    "Estimated future disease risk at ages 25 to 45 from a medical report. Not a diagnostic tool.",
};

/**
 * Applies the stored theme before first paint.
 *
 * Without this the page renders in light mode and then flips to dark once
 * React hydrates — a visible flash on every load. Runs synchronously in <head>,
 * so it must not depend on any bundle.
 */
const THEME_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem('hrp.theme');
    var choice = (stored === 'light' || stored === 'dark' || stored === 'system')
      ? stored : 'system';
    var resolved = choice === 'system'
      ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : choice;
    document.documentElement.setAttribute('data-theme', resolved);
    document.documentElement.style.colorScheme = resolved;
  } catch (e) {
    document.documentElement.setAttribute('data-theme', 'light');
  }
})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <SettingsProvider>
          <AnalysisProvider>
            <AppHeader />
            {children}
          </AnalysisProvider>
        </SettingsProvider>
      </body>
    </html>
  );
}
