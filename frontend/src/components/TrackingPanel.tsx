import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Cpu,
  Crosshair,
  Home,
  Loader2,
  Plug,
  Power,
  RotateCcw,
  Target,
} from "lucide-react"
import { trackingApi } from "@/lib/trackingApi"
import type { Camera, HardwareStatus, TrackingStatus } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

interface TrackingPanelProps {
  camera: Camera
  canControl: boolean
}

const STEP_SIZE = 5 // degrees per manual click

export default function TrackingPanel({ camera, canControl }: TrackingPanelProps) {
  const queryClient = useQueryClient()
  const [connectOpen, setConnectOpen] = useState(false)
  const [portInput, setPortInput] = useState("COM3")

  // Hardware status query
  const hwQuery = useQuery<HardwareStatus>({
    queryKey: ["hardware", "status"],
    queryFn: trackingApi.getHardwareStatus,
    refetchInterval: 3000,
  })

  // Tracking status query for this specific camera
  const trackingQuery = useQuery<TrackingStatus>({
    queryKey: ["tracking", camera.id],
    queryFn: () => trackingApi.getTrackingStatus(camera.id),
    refetchInterval: 1000,
  })

  // Mutations
  const connectMutation = useMutation({
    mutationFn: () => trackingApi.connectHardware(portInput),
    onSuccess: () => {
      toast.success(`Connected to Arduino on ${portInput}`)
      setConnectOpen(false)
      queryClient.invalidateQueries({ queryKey: ["hardware"] })
    },
    onError: (err: Error) => toast.error(`Connection failed: ${err.message}`),
  })

  const disconnectMutation = useMutation({
    mutationFn: trackingApi.disconnectHardware,
    onSuccess: () => {
      toast.info("Arduino disconnected")
      queryClient.invalidateQueries({ queryKey: ["hardware"] })
      queryClient.invalidateQueries({ queryKey: ["tracking", camera.id] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const toggleTrackingMutation = useMutation({
    mutationFn: (currentlyEnabled: boolean) =>
      currentlyEnabled
        ? trackingApi.stopTracking(camera.id)
        : trackingApi.startTracking(camera.id),
    onSuccess: (data) => {
      toast.success(data.enabled ? "Autonomous tracking enabled" : "Tracking disabled")
      queryClient.invalidateQueries({ queryKey: ["tracking", camera.id] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const homeMutation = useMutation({
    mutationFn: () => trackingApi.homeServos(camera.id),
    onSuccess: () => {
      toast.success("Camera centered")
      queryClient.invalidateQueries({ queryKey: ["tracking", camera.id] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const manualMoveMutation = useMutation({
    mutationFn: ({ pan, tilt }: { pan: number; tilt: number }) =>
      trackingApi.manualMove(camera.id, pan, tilt),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tracking", camera.id] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const hw = hwQuery.data
  const tracking = trackingQuery.data
  const isArduinoConnected = Boolean(hw?.connected)
  const isTrackingActive = Boolean(tracking?.enabled)
  const isCameraActive = camera.status === "active"

  const curPan = tracking?.pan ?? 90
  const curTilt = tracking?.tilt ?? 90

  // Manual step handler
  const handleStep = (panDelta: number, tiltDelta: number) => {
    if (isTrackingActive) {
      toast.warning("Disable autonomous tracking to use manual controls")
      return
    }
    const newPan = Math.max(30, Math.min(150, curPan + panDelta))
    const newTilt = Math.max(45, Math.min(135, curTilt + tiltDelta))
    manualMoveMutation.mutate({ pan: newPan, tilt: newTilt })
  }

  // State badge styling & label
  const renderStateBadge = () => {
    if (!isArduinoConnected) {
      return (
        <Badge variant="outline" className="border-amber-500/40 text-amber-500">
          <Plug className="mr-1 h-3 w-3" /> Arduino Offline
        </Badge>
      )
    }
    if (!isCameraActive) {
      return (
        <Badge variant="outline" className="text-muted-foreground">
          Camera Inactive
        </Badge>
      )
    }
    if (!isTrackingActive) {
      return (
        <Badge variant="outline" className="text-muted-foreground">
          Tracking Off
        </Badge>
      )
    }

    switch (tracking?.state) {
      case "tracking":
        return (
          <Badge variant="success" className="animate-pulse">
            <Target className="mr-1 h-3 w-3" /> Tracking ID: {tracking.target_track_id ?? "—"}
          </Badge>
        )
      case "target_lost":
        return (
          <Badge variant="warning">
            <Crosshair className="mr-1 h-3 w-3" /> Target Lost
          </Badge>
        )
      case "error":
        return (
          <Badge variant="destructive">
            Hardware Error
          </Badge>
        )
      default:
        return <Badge variant="secondary">Idle</Badge>
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-b-md border-t border-border bg-card/60 p-2.5 text-xs">
      {/* Top row: Status, Angles readout, Tracking Toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          {renderStateBadge()}
          <span className="font-mono text-[11px] text-muted-foreground">
            Pan: {curPan.toFixed(1)}° | Tilt: {curTilt.toFixed(1)}°
          </span>
        </div>

        <div className="flex items-center gap-1">
          {/* Arduino Connect / Settings Dialog */}
          <Dialog open={connectOpen} onOpenChange={setConnectOpen}>
            <DialogTrigger asChild>
              <Button
                size="sm"
                variant="ghost"
                className="h-6 px-1.5 text-xs text-muted-foreground hover:text-foreground"
                title={isArduinoConnected ? `Connected on ${hw?.port}` : "Connect Arduino"}
              >
                <Cpu className="h-3.5 w-3.5" />
                <span className="ml-1 hidden sm:inline">
                  {isArduinoConnected ? hw?.port : "Connect"}
                </span>
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-sm">
              <DialogHeader>
                <DialogTitle>Arduino Servo Controller</DialogTitle>
              </DialogHeader>
              <div className="flex flex-col gap-3 py-2">
                <div className="flex flex-col gap-1.5">
                  <Label>Serial Port</Label>
                  <Input
                    placeholder="COM3 or /dev/ttyACM0"
                    value={portInput}
                    onChange={(e) => setPortInput(e.target.value)}
                  />
                  {hw?.available_ports && hw.available_ports.length > 0 && (
                    <span className="text-[11px] text-muted-foreground">
                      Detected ports: {hw.available_ports.join(", ")}
                    </span>
                  )}
                </div>

                <div className="flex justify-between pt-2">
                  {isArduinoConnected ? (
                    <Button
                      variant="destructive"
                      size="sm"
                      disabled={disconnectMutation.isPending}
                      onClick={() => disconnectMutation.mutate()}
                    >
                      {disconnectMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
                      Disconnect
                    </Button>
                  ) : (
                    <div />
                  )}
                  <Button
                    size="sm"
                    disabled={!portInput || connectMutation.isPending}
                    onClick={() => connectMutation.mutate()}
                  >
                    {connectMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
                    Connect
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>

          {/* Autonomous Tracking Start/Stop Button */}
          {canControl && (
            <Button
              size="sm"
              variant={isTrackingActive ? "destructive" : "default"}
              className="h-6 px-2 text-xs"
              disabled={
                !isArduinoConnected ||
                !isCameraActive ||
                toggleTrackingMutation.isPending
              }
              onClick={() => toggleTrackingMutation.mutate(isTrackingActive)}
            >
              {toggleTrackingMutation.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : isTrackingActive ? (
                <>
                  <Power className="mr-1 h-3 w-3" /> Stop Tracking
                </>
              ) : (
                <>
                  <Crosshair className="mr-1 h-3 w-3" /> Follow Person
                </>
              )}
            </Button>
          )}
        </div>
      </div>

      {/* Manual Pan & Tilt Controls (Visible when tracking is idle or stopped) */}
      {canControl && isArduinoConnected && (
        <div className="flex items-center justify-between border-t border-border/40 pt-1.5">
          <span className="text-[11px] text-muted-foreground">
            {isTrackingActive ? "Manual control locked during autonomous tracking" : "Manual Positioning"}
          </span>

          <TooltipProvider>
            <div className="flex items-center gap-1">
              {/* Home center */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="icon"
                    variant="outline"
                    className="h-6 w-6"
                    disabled={isTrackingActive || homeMutation.isPending}
                    onClick={() => homeMutation.mutate()}
                  >
                    <Home className="h-3 w-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Center Camera (90°, 90°)</TooltipContent>
              </Tooltip>

              {/* Pan Left */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="icon"
                    variant="outline"
                    className="h-6 w-6"
                    disabled={isTrackingActive || curPan <= 30}
                    onClick={() => handleStep(-STEP_SIZE, 0)}
                  >
                    <ArrowLeft className="h-3 w-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Pan Left (-5°)</TooltipContent>
              </Tooltip>

              {/* Tilt Up */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="icon"
                    variant="outline"
                    className="h-6 w-6"
                    disabled={isTrackingActive || curTilt <= 45}
                    onClick={() => handleStep(0, -STEP_SIZE)}
                  >
                    <ArrowUp className="h-3 w-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Tilt Up (-5°)</TooltipContent>
              </Tooltip>

              {/* Tilt Down */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="icon"
                    variant="outline"
                    className="h-6 w-6"
                    disabled={isTrackingActive || curTilt >= 135}
                    onClick={() => handleStep(0, STEP_SIZE)}
                  >
                    <ArrowDown className="h-3 w-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Tilt Down (+5°)</TooltipContent>
              </Tooltip>

              {/* Pan Right */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="icon"
                    variant="outline"
                    className="h-6 w-6"
                    disabled={isTrackingActive || curPan >= 150}
                    onClick={() => handleStep(STEP_SIZE, 0)}
                  >
                    <ArrowRight className="h-3 w-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Pan Right (+5°)</TooltipContent>
              </Tooltip>
            </div>
          </TooltipProvider>
        </div>
      )}
    </div>
  )
}
