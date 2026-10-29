import { useCallback, useState, useRef } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { useLiveFeed, type LiveEvent } from "@/lib/ws"
import type { Camera, CameraStatus, Incident } from "@/lib/types"
import CameraTile from "@/components/CameraTile"
import IncidentCard from "@/components/IncidentCard"
import CampusSchematic from "@/components/CampusSchematic"
import { ScrollArea } from "@/components/ui/scroll-area"

export default function Dashboard() {
  const { user } = useAuth()
  // Responders can view cameras but not start/stop them — same split as
  // evidence (view yes, create/package no). Hiding the control avoids
  // offering a button that would just 403.
  const canControlCameras = user?.role === "admin" || user?.role === "operator"
  const queryClient = useQueryClient()
  const tileRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const [pendingId, setPendingId] = useState<number | null>(null)

  const camerasQuery = useQuery({
    queryKey: ["cameras"],
    queryFn: () => api.get<Camera[]>("/cameras"),
    refetchInterval: 8000,
  })

  const toggleMutation = useMutation({
    mutationFn: (camera: Camera) =>
      camera.status === "active"
        ? api.post<{ camera_id: number; status: CameraStatus }>(`/cameras/${camera.id}/stop`)
        : api.post<{ camera_id: number; status: CameraStatus }>(`/cameras/${camera.id}/start`),
    onMutate: (camera) => setPendingId(camera.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
    onError: (e: Error) => toast.error(e.message),
    onSettled: () => setPendingId(null),
  })
  const incidentsQuery = useQuery({
    queryKey: ["incidents", "open"],
    queryFn: () => api.get<Incident[]>("/incidents?limit=50"),
    refetchInterval: 8000,
  })

  const handleEvent = useCallback(
    (event: LiveEvent) => {
      // A NEW_ALERT can be a camera-health observation (offline/frozen/blackout)
      // or a person-detection event that may have created/extended an incident —
      // the payload doesn't distinguish cheaply, so refresh both.
      if (event.type === "NEW_ALERT") {
        queryClient.invalidateQueries({ queryKey: ["cameras"] })
        queryClient.invalidateQueries({ queryKey: ["incidents"] })
      }
    },
    [queryClient]
  )
  useLiveFeed(handleEvent)

  const cameras = camerasQuery.data ?? []
  const incidents = (incidentsQuery.data ?? []).filter((i) => i.status !== "resolved")

  return (
    <div className="grid gap-4 p-4 lg:grid-cols-[1fr_360px]">
      <div className="flex flex-col gap-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {cameras.map((cam) => (
            <div key={cam.id} ref={(el) => { tileRefs.current[cam.id] = el }}>
              <CameraTile
                camera={cam}
                pending={pendingId === cam.id}
                onToggle={canControlCameras ? (c) => toggleMutation.mutate(c) : undefined}
              />
            </div>
          ))}
          {cameras.length === 0 && (
            <p className="col-span-full text-sm text-muted-foreground">No cameras configured yet. Add one from Configuration.</p>
          )}
        </div>
        <CampusSchematic
          cameras={cameras}
          onSelect={(id) => tileRefs.current[id]?.scrollIntoView({ behavior: "smooth", block: "center" })}
        />
      </div>
      <div className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-muted-foreground">Open Incidents ({incidents.length})</h2>
        <ScrollArea className="h-[calc(100vh-7.5rem)] pr-2">
          <div className="flex flex-col gap-2">
            {incidents.map((incident) => (
              <IncidentCard key={incident.id} incident={incident} />
            ))}
            {incidents.length === 0 && <p className="text-sm text-muted-foreground">No open incidents.</p>}
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}
