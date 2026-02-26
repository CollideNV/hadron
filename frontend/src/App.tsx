import { Routes, Route } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import CRListPage from "./pages/CRListPage";
import CRDetailPage from "./pages/CRDetailPage";
import NewCRPage from "./pages/NewCRPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<CRListPage />} />
        <Route path="/cr/:crId" element={<CRDetailPage />} />
        <Route path="/new" element={<NewCRPage />} />
      </Routes>
    </AppShell>
  );
}
