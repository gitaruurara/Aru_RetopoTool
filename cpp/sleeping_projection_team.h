#pragma once
#include <algorithm>
#include <atomic>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <functional>
#include <future>
#include <vector>
#include <memory>
class AruProjectionTeam {
    std::mutex mutex;
    std::condition_variable wake, done;
    std::vector<std::thread> workers;
    std::function<void()> job;
    unsigned generation=0;
    int remaining=0;
    bool stopping=false;
public:
    const int size;
    explicit AruProjectionTeam(int count):size(count) {
        try {
            for(int i=1;i<count;++i)workers.emplace_back([this]{
                unsigned seen=0;
                for(;;){
                    std::unique_lock<std::mutex> lock(mutex);
                    wake.wait(lock,[&]{return stopping || generation!=seen;});
                    if(stopping)return;
                    seen=generation;auto task=job;lock.unlock();task();lock.lock();
                    if(--remaining==0)done.notify_one();
                }
            });
        } catch(...) {stop();throw;}
    }
    void stop(){
        {std::lock_guard<std::mutex> lock(mutex);stopping=true;}
        wake.notify_all();for(auto& worker:workers)if(worker.joinable())worker.join();
    }
    ~AruProjectionTeam(){stop();}
    template<class F> void run(int n,F fn,int chunk=128){
        std::atomic<int> cursor{0};std::exception_ptr error;std::mutex errors;
        auto work=[&]{try{
            for(;;){int start=cursor.fetch_add(chunk,std::memory_order_relaxed);if(start>=n)return;
                for(int i=start;i<std::min(n,start+chunk);++i)fn(i);}
        }catch(...){std::lock_guard<std::mutex> lock(errors);if(!error)error=std::current_exception();}};
        {std::lock_guard<std::mutex> lock(mutex);job=work;remaining=int(workers.size());++generation;}
        wake.notify_all();work();
        {std::unique_lock<std::mutex> lock(mutex);done.wait(lock,[&]{return remaining==0;});job={};}
        if(error)std::rethrow_exception(error);
    }
};
