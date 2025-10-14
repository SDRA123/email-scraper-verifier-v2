import React, { useState } from 'react';
import {
  Container,
  Paper,
  TextField,
  Button,
  Typography,
  Box,
  Alert,
  Avatar,
  Grid,
  Link,
} from '@mui/material';
import LogoImage from '../Logos and icons/logo/Aurora Photon (3).png';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../services/authService';
import { LoginCredentials, RegisterData } from '../types';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`auth-tabpanel-${index}`}
      aria-labelledby={`auth-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

const Login: React.FC = () => {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(false);

  const [loginForm, setLoginForm] = useState<LoginCredentials>({
    username: '',
    password: '',
  });

  // registration removed: app uses admin-created users

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      await login(loginForm);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  // registration removed

  return (
    <Container component="main" maxWidth="xs">
      <Box
        sx={{
          marginTop: 8,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        <Paper elevation={6} sx={{ width: '100%', p: 4 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', flexDirection: 'column', mb: 2 }}>
            <Avatar
              src={LogoImage}
              alt="Websift logo"
              sx={{ bgcolor: 'transparent', width: 72, height: 72, mb: 1 }}
            />
            <Typography component="h1" variant="h5">
              Websift
            </Typography>
            <Typography variant="caption" color="text.secondary">Sign in to continue</Typography>
          </Box>

          {error && (
            <Box sx={{ mb: 2 }}>
              <Alert severity="error">{error}</Alert>
            </Box>
          )}

          <Box component="form" onSubmit={handleLogin} noValidate>
            <TextField
              margin="normal"
              required
              fullWidth
              id="username"
              label="Username"
              name="username"
              autoComplete="username"
              autoFocus
              value={loginForm.username}
              onChange={(e) => setLoginForm({ ...loginForm, username: e.target.value })}
            />
            <TextField
              margin="normal"
              required
              fullWidth
              name="password"
              label="Password"
              type="password"
              id="password"
              autoComplete="current-password"
              value={loginForm.password}
              onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
            />

            <Button type="submit" fullWidth variant="contained" sx={{ mt: 3, mb: 2 }} disabled={loading}>
              {loading ? 'Signing In...' : 'Sign In'}
            </Button>

            <Grid container>
              <Grid item xs>
                <Link href="#" variant="body2" onClick={(e) => e.preventDefault()}>
                  Forgot password?
                </Link>
              </Grid>
              <Grid item>
                <Typography variant="caption" color="text.secondary">Contact admin to create accounts.</Typography>
              </Grid>
            </Grid>
          </Box>

          <Box sx={{ mt: 3, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">Version 1.0</Typography>
          </Box>
        </Paper>
      </Box>
    </Container>
  );
};

export default Login;