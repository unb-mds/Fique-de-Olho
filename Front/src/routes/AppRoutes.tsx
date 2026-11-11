import { Routes, Route } from 'react-router-dom';
import HomePage from '@/pages/HomePage';
import EditalDetailPage from '@/pages/EditalDetailPage';
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import NotificationsPage from "@/pages/NotificationsPage";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/editais/:id" element={<EditalDetailPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/notifications" element={<NotificationsPage />} />
    </Routes>
  );
}
