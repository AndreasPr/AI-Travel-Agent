import "leaflet/dist/leaflet.css";
import "./globals.css";
export const metadata = {
  title: "Elsewhere — A considered trip planner",
  description: "Plan and refine a sourced itinerary, one conversation at a time.",
};
export default function RootLayout({ children }) {
  return <html lang="en"><body>{children}</body></html>;
}
