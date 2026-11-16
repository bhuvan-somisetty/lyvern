export function LogoutButton({ action }: { action: () => void | Promise<void> }) {
  return (
    <form action={action}>
      <button type="submit" className="text-sm text-muted hover:underline">
        Sign out
      </button>
    </form>
  );
}
