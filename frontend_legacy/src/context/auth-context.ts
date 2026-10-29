import { createContext } from 'react';
import type { UserMeResponse } from '../types/api';

export interface AuthContextType {
  user: UserMeResponse | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (token: string, user: UserMeResponse) => void;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);
