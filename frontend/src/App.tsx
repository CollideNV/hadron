import { Routes, Route } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import ErrorBoundary from "./components/shared/ErrorBoundary";
import CRListPage from "./pages/CRListPage";
import CRDetailPage from "./pages/CRDetailPage";
import NewCRPage from "./pages/NewCRPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<CRListPage />} />
        <Route path="/cr/:crId/:stage?" element={<ErrorBoundary><CRDetailPage /></ErrorBoundary>} />
        <Route path="/new" element={<NewCRPage />} />
      </Routes>
    </AppShell>
  );
}
