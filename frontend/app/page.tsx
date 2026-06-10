import Chat from "@/components/Chat";

export default function Home() {
  return (
    <main className="mx-auto flex h-[100dvh] max-w-3xl flex-col sm:py-5">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-white/75 shadow-soft ring-1 ring-slate-200/70 backdrop-blur-xl sm:rounded-[28px]">
        <Chat />
      </div>
    </main>
  );
}
