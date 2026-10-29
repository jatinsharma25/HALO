import type { ReactNode } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import { useAuth } from "@/lib/auth"
import AppShell from "@/components/AppShell"
import LandingPage from "@/pages/LandingPage"
import Login from "@/pages/Login"
import Dashboard from "@/pages/Dashboard"
import IncidentDetail from "@/pages/IncidentDetail"
import Configuration from "@/pages/Configuration"
import Governance from "@/pages/Governance"

function ProtectedRoute({ children, roles }: { children: ReactNode; roles?: string[] }) {
  const { user, loading } = useAuth()
  if (loading) {
    return <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">Loading…</div>
  }
  if (!user) return <Navigate to="/login" replace />
  if (roles && !roles.includes(user.role)) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

export default function AppRoutes() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<Login />} />

      {/* Protected — wrapped in AppShell (nav + logout) */}
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/incidents/:id" element={<IncidentDetail />} />
        <Route
          path="/config"
          element={
            <ProtectedRoute roles={["admin"]}>
              <Configuration />
            </ProtectedRoute>
          }
        />
        <Route path="/governance" element={<Governance />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
