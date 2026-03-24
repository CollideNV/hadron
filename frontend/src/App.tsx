import { Routes, Route, Navigate } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import ErrorBoundary from "./components/shared/ErrorBoundary";
import CRListPage from "./pages/CRListPage";
import CRDetailPage from "./pages/CRDetailPage";
import PromptsPage from "./pages/PromptsPage";
import SettingsPage from "./pages/SettingsPage";
import AuditLogPage from "./pages/AuditLogPage";
import AnalyticsPage from "./pages/AnalyticsPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<CRListPage />} />
        <Route path="/cr/:crId/:stage?" element={<ErrorBoundary><CRDetailPage /></ErrorBoundary>} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/prompts" element={<PromptsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/audit" element={<AuditLogPage />} />
        <Route path="/new" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
