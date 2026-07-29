import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

const plusJakarta = Plus_Jakarta_Sans({
  variable: "--font-plus-jakarta",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
});

export const metadata = {
  title: "DataSense AI — Talk to Your Data",
  description:
    "Upload your Excel, CSV, JSON, or connect your SQL database and instantly generate AI-powered insights and interactive dashboards.",
  keywords: ["data visualization", "AI dashboard", "natural language analytics", "data insights"],
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${plusJakarta.variable} h-full`}>
      <body className="min-h-full app-bg">{children}</body>
    </html>
  );
}
