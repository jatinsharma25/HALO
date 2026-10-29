import { useState } from "react"
import { AlertTriangle, Eye, EyeOff, Loader2, VideoOff, WifiOff } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { getToken } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { cn } from "@/lib/utils"
import type { Camera } from "@/lib/types"
import TrackingPanel from "@/components/TrackingPanel"

const STATUS_META: Record<Camera["status"], { label: string; variant: "success" | "destructive" | "warning" | "secondary"; icon?: typeof WifiOff }> = {
  active: { label: "Active", variant: "success" },
  unknown: { label: "Not started", variant: "secondary" },
  offline: { label: "Offline", variant: "destructive", icon: WifiOff },
  frozen: { label: "Frozen feed", variant: "warning", icon: VideoOff },
  blackout: { label: "Blackout / covered", variant: "destructive", icon: EyeOff },
  blurred: { label: "Severe blur", variant: "warning", icon: AlertTriangle },
}

export default function CameraTile({
  camera,
  pending,
  onToggle,
}: {
  camera: Camera
  pending?: boolean
  onToggle?: (camera: Camera) => void
}) {
  const meta = STATUS_META[camera.status] ?? STATUS_META.unknown
  // "blackout" still has a real (near-black) frame to show — rendering it
  // is what actually distinguishes "covered" from a truly dead source in
  // the tile, instead of both falling back to the same WifiOff placeholder.
  const showVideo =
    camera.status === "active" ||
    camera.status === "frozen" ||
    camera.status === "blurred" ||
    camera.status === "blackout"
  const token = getToken()
  const { user } = useAuth()
  const canControl = user?.role === "admin" || user?.role === "operator"
  const [privacyBlur, setPrivacyBlur] = useState(true)

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0 py-2.5">
        <span className="truncate text-sm font-medium">{camera.name}</span>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            size="icon"
            variant={privacyBlur ? "default" : "ghost"}
            className="h-6 w-6"
            title={privacyBlur ? "Blurring faces — click to show raw feed" : "Blur faces on this feed"}
            onClick={() => setPrivacyBlur((v) => !v)}
          >
            {privacyBlur ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </Button>
          <Badge variant={meta.variant} className="gap-1">
            {meta.icon && <meta.icon className="h-3 w-3" />}
            {meta.label}
          </Badge>
          {onToggle && (
            <Button
              size="sm"
              variant={camera.status === "active" ? "destructive" : "default"}
              className="h-6 px-2 text-xs"
              disabled={pending}
              onClick={() => onToggle(camera)}
            >
              {pending ? <Loader2 className="h-3 w-3 animate-spin" /> : camera.status === "active" ? "Stop" : "Start"}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className={cn("relative aspect-video w-full bg-black")}>
          {showVideo ? (
            <img
              src={`/api/stream/${camera.id}?token=${encodeURIComponent(token ?? "")}&blur=${privacyBlur}`}
              alt={camera.name}
              className="h-full w-full object-contain"
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-muted-foreground">
              <WifiOff className="h-6 w-6" />
              <span className="text-xs">No signal</span>
            </div>
          )}
        </div>
      </CardContent>
      <TrackingPanel camera={camera} canControl={canControl} />
    </Card>
  )
}
