import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { ProtectedRoute } from './components/layout/ProtectedRoute';
import { AppLayout } from './components/layout/AppLayout';

// Pages
import { LandingPage } from './pages/LandingPage';
import { DirectoryManager } from './pages/DirectoryManager';
import { Login } from './pages/Login';
import { Operations } from './pages/Operations';
import { Incidents } from './pages/Incidents';
import { Casebook } from './pages/Casebook';
import { Configuration } from './pages/Configuration';
import { Governance } from './pages/Governance';

import './App.css';

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Router>
          <Routes>
            {/* Public Routes */}
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<Login />} />

            {/* Protected Application Routes — wrapped in AppLayout sidebar */}
            <Route element={<ProtectedRoute />}>
              <Route element={<AppLayout />}>
                <Route path="/operations" element={<Operations />} />
                <Route path="/operations/camera/:cameraId" element={<Operations />} />
                <Route path="/directory" element={<DirectoryManager />} />
                <Route path="/incidents" element={<Incidents />} />
                <Route path="/casebook" element={<Casebook />} />
                <Route path="/configuration" element={<Configuration />} />
                <Route path="/governance" element={<Governance />} />
              </Route>
            </Route>

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Router>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
