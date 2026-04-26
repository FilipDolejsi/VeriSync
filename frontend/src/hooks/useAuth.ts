import { useEffect, useState } from 'react';
import { api, User } from '../lib/api';

export function useAuth() {
  const [user, setUser]       = useState<User | null | undefined>(undefined); // undefined = loading
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.me()
      .then(u => { setUser(u); setLoading(false); })
      .catch(() => { setUser(null); setLoading(false); });
  }, []);

  const logout = async () => {
    await api.logout().catch(() => {});
    setUser(null);
    window.location.href = '/';
  };

  return { user, loading, logout };
}
