"use client"
import performAPIGetRequest from '@/app/utils/apiClient'
import Error from 'next/error'
import {notFound} from 'next/navigation'

export default function FlightDetailPage({params}){  
    const {id} = params

    const path = `/flights/${id}`
    const { data, error, isLoading } = performAPIGetRequest(path)

    if (error){
        if (error.statusCode === 404){
            notFound()
        }
        return <Error statusCode={error.statusCode}/>
    }


    if (isLoading) return <div>loading...</div>


    return <div>{JSON.stringify(data)}</div>
}