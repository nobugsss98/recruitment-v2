import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { Toaster } from 'sonner';
import { AuthProvider } from './context/AuthContext';
import { Layout } from './components/Layout';
import { ProtectedRoute, RoleRoute } from './components/guards';
import { LoginPage } from './pages/Login';
import { DashboardPage } from './pages/Dashboard';
import { JobDetailPage } from './pages/JobDetail';
import { ScreeningPage } from './pages/Screening';
import { InterviewsPage } from './pages/Interviews';
import { ExecutivePage } from './pages/Executive';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="/jobs/:id" element={<JobDetailPage />} />
          <Route
            path="/jobs/:id/screening"
            element={
              <RoleRoute roles={['hr', 'interviewer']}>
                <ScreeningPage />
              </RoleRoute>
            }
          />
          <Route
            path="/interviews"
            element={
              <RoleRoute roles={['hr', 'interviewer']}>
                <InterviewsPage />
              </RoleRoute>
            }
          />
          <Route
            path="/executive"
            element={
              <RoleRoute roles={['hr', 'ceo']}>
                <ExecutivePage />
              </RoleRoute>
            }
          />
        </Route>
        <Route path="*" element={<LoginPage />} />
      </Routes>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <AnimatedRoutes />
        </BrowserRouter>
        <Toaster
          theme="dark"
          position="top-right"
          toastOptions={{
            style: {
              background: '#141a29',
              border: '1px solid rgba(255,255,255,0.1)',
              color: '#fff',
            },
          }}
        />
      </AuthProvider>
    </QueryClientProvider>
  );
}
