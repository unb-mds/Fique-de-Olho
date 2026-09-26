import { Routes, Route } from 'react-router-dom';
import HomePage from '@/pages/HomePage';
import EditalDetailPage from '@/pages/EditalDetailPage';

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/editais/:id" element={<EditalDetailPage />} />
    </Routes>
  );
}
