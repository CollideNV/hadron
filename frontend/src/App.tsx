import { Routes, Route, Navigate } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import ErrorBoundary from "./components/shared/ErrorBoundary";
import CRListPage from "./pages/CRListPage";
import CRDetailPage from "./pages/CRDetailPage";
import PromptsPage from "./pages/PromptsPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<CRListPage />} />
        <Route path="/cr/:crId/:stage?" element={<ErrorBoundary><CRDetailPage /></ErrorBoundary>} />
        <Route path="/prompts" element={<PromptsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/new" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
