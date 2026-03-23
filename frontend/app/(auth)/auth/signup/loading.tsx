import { Skeleton } from "@/components/ui/skeleton";

export default function SignupLoading() {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Skeleton variant="text" className="mx-auto h-9 w-60" />
        <Skeleton variant="text" className="mx-auto mt-2 h-4 w-64" />
      </div>
      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10 space-y-6">
          <Skeleton variant="text" className="h-4 w-24" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
          <Skeleton variant="text" className="h-4 w-20" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
          <Skeleton variant="text" className="h-4 w-32" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
        </div>
      </div>
    </div>
  );
}
