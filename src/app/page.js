"use client" // make for client component only
import FlightListPage from '@/app/flights/page'
import FlightPredictForm from '@/app/flights/forms'

export default function Home() {
  return <div>
      <FlightPredictForm />
      {/* <FlightListPage /> */}
  </div>
}
