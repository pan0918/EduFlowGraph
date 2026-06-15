import { WorkspaceProvider } from "@/components/providers/WorkspaceProvider";
import { WorkspaceSidebar } from "@/components/sidebar/WorkspaceSidebar";

export default function WorkspaceLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <WorkspaceProvider>
      <div className="flex min-h-screen flex-col overflow-hidden bg-[var(--background)] lg:h-screen lg:flex-row">
        <WorkspaceSidebar />
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </WorkspaceProvider>
  );
}
