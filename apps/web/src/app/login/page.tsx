import { Suspense } from "react";
import { login } from "@/app/actions";
import { Loading } from "@/components/Loading";
import { LoginForm } from "@/components/LoginForm";

async function LoginContent({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  return <LoginForm error={error} action={login} />;
}

export default function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  return (
    <Suspense fallback={<Loading label="Loading" />}>
      <LoginContent searchParams={searchParams} />
    </Suspense>
  );
}
