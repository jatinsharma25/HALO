import { NavLink, Outlet } from "react-router-dom"
import { Camera, LayoutDashboard, ShieldCheck, Sliders, LogOut, Sun, Moon } from "lucide-react"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth"
import { useTheme } from "@/lib/theme"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

const NAV_ITEMS = [
  { to: "/dashboard", label: "Operations", icon: LayoutDashboard, roles: ["admin", "operator", "responder"] },
  { to: "/config", label: "Configuration", icon: Sliders, roles: ["admin"] },
  { to: "/governance", label: "Governance", icon: ShieldCheck, roles: ["admin", "operator", "responder"] },
]

export default function AppShell() {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 flex h-14 shrink-0 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur">
        <div className="flex items-center gap-2 font-semibold">
          <Camera className="h-5 w-5 text-primary" />
          <span className="hidden sm:inline">EyeSpy</span>
          <span className="sm:hidden">EyeSpy</span>
        </div>
        <nav className="flex items-center gap-1">
          {NAV_ITEMS.filter((item) => !user || item.roles.includes(user.role)).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium transition-colors",
                  isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                )
              }
            >
              <item.icon className="h-4 w-4" />
              <span className="hidden md:inline">{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          {user && (
            <div className="hidden text-right text-xs leading-tight sm:block">
              <div className="font-medium">{user.username}</div>
              <Badge variant="outline" className="text-[10px] capitalize">{user.role}</Badge>
            </div>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
          <Button variant="ghost" size="icon" onClick={logout} title="Log out">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </header>
      <main className="flex-1 bg-background">
        <Outlet />
      </main>
    </div>
  )
}
