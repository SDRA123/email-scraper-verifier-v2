import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { CssBaseline, Container, CircularProgress, Box } from '@mui/material';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import UserManagement from './pages/UserManagement';
import EmailVerification from './pages/EmailVerification';
import DataManagement from './pages/DataManagement';
import Navigation from './components/Navigation';
import { AuthProvider, useAuth } from './services/authService';
import { ThemeProviderWrapper } from './contexts/ThemeContext';

const PrivateRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
};

function App() {
  return (
    <ThemeProviderWrapper>
      <CssBaseline />
      <AuthProvider>
        <Router>
          <div className="App">
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                path="/*"
                element={
                  <PrivateRoute>
                    <Navigation />
                    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
                      <Routes>
                        <Route path="/" element={<Navigate to="/dashboard" />} />
                        <Route path="/dashboard" element={<Dashboard />} />
                        <Route path="/users" element={<UserManagement />} />
                        <Route path="/email-verification" element={<EmailVerification />} />
                        <Route path="/data-management" element={<DataManagement />} />
                      </Routes>
                    </Container>
                  </PrivateRoute>
                }
              />
            </Routes>
          </div>
        </Router>
      </AuthProvider>
    </ThemeProviderWrapper>
  );
}

export default App;