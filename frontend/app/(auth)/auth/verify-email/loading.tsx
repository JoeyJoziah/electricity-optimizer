export default function VerifyEmailLoading() {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
      <p className="mt-4 text-sm text-gray-500">Verifying your email...</p>
    </div>
  );
}
